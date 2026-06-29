from __future__ import annotations

import json
import unittest
from unittest import mock

from harness.cli import model_discovery


class ModelDiscoveryTests(unittest.TestCase):
    def test_env_choices_win_for_provider(self) -> None:
        choices = model_discovery.model_choices(
            "claude", {"AI_HARNESS_CLAUDE_MODEL_CHOICES": "sonnet, opus"}
        )

        self.assertEqual(["sonnet", "opus"], [choice.value for choice in choices])

    @mock.patch.object(model_discovery.shutil, "which", return_value="/bin/codex")
    @mock.patch.object(model_discovery.subprocess, "run")
    def test_codex_bundled_catalog_lists_visible_models(self, run, _which) -> None:
        run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "models": [
                        {"slug": "gpt-5.5", "display_name": "GPT-5.5", "visibility": "list"},
                        {"slug": "hidden", "display_name": "Hidden", "visibility": "hidden"},
                    ]
                }
            ),
        )

        choices = model_discovery.model_choices("codex", {})

        self.assertEqual(["gpt-5.5"], [choice.value for choice in choices])
        self.assertEqual(["GPT-5.5"], [choice.label for choice in choices])
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
