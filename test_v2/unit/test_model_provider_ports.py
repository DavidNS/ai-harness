from __future__ import annotations

from pathlib import Path
import unittest

from harness_v2.adapters.models import FakeModelProvider, ScriptedModelProvider
from harness_v2.backend.ports.model_provider import (
    CapabilityProjection,
    McpToolCapability,
    ModelProviderRequest,
    ModelProviderResult,
    ModelSelection,
    PathCapability,
    TimeoutPolicy,
    TruncationPolicy,
)


class ModelProviderPortTests(unittest.TestCase):
    def request(self, prompt: str = "inspect") -> ModelProviderRequest:
        return ModelProviderRequest(
            prompt=prompt,
            working_directory=Path.cwd(),
            model=ModelSelection("fake", "test-model"),
            capabilities=CapabilityProjection(paths=(PathCapability("**", "read"),), skills=("skill-a",)),
            timeout=TimeoutPolicy(17),
            truncation=TruncationPolicy(64),
        )

    def test_request_and_result_dtos_normalize_valid_data(self) -> None:
        request = self.request("  inspect  ")
        result = ModelProviderResult("out", "err", 0, 0.1)

        self.assertEqual("inspect", request.prompt)
        self.assertEqual("fake", request.model.provider)
        self.assertTrue(result.succeeded)

    def test_capabilities_validate_modes_and_duplicates(self) -> None:
        with self.assertRaises(ValueError):
            PathCapability("**", "admin")
        with self.assertRaises(ValueError):
            McpToolCapability("docs", "search", "admin")
        with self.assertRaises(ValueError):
            CapabilityProjection(skills=("same", "same"))

    def test_timeout_and_truncation_policies_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            TimeoutPolicy(0)
        with self.assertRaises(ValueError):
            TruncationPolicy(0)

    def test_fake_provider_records_requests_and_returns_canned_result(self) -> None:
        canned = ModelProviderResult("ok", "", 0, 0.0)
        provider = FakeModelProvider([canned])
        request = self.request()

        result = provider.run(request)

        self.assertIs(canned, result)
        self.assertEqual([request], provider.requests)

    def test_scripted_provider_covers_success_failure_timeout_malformed_and_truncation(self) -> None:
        provider = ScriptedModelProvider()

        self.assertTrue(provider.run(self.request("hello")).succeeded)
        self.assertEqual(7, provider.run(self.request("FAIL now")).exit_code)
        self.assertTrue(provider.run(self.request("TIMEOUT now")).timed_out)
        self.assertEqual("not json", provider.run(self.request("MALFORMED now")).stdout)
        self.assertTrue(provider.run(self.request("LARGE now")).truncated)


if __name__ == "__main__":
    unittest.main()
