import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "harness"
sys.path.insert(0, str(SCRIPTS))
from ai_harness.providers.base import ProviderResult
from ai_harness.providers.json_extract import JsonOutputError, extract_json_object, run_json_prompt

class RecordingProvider:
    def __init__(self, outputs):
        self.outputs, self.prompts = list(outputs), []
    def run_prompt(self, prompt, *, cwd, permissions=None):
        self.prompts.append(prompt)
        return ProviderResult(self.outputs.pop(0), "", 0, 0.01)

def require_answer(value):
    if set(value) != {"answer"} or not isinstance(value["answer"], int):
        raise ValueError("answer must be an integer")
    return value["answer"]

class JsonExtractionTests(unittest.TestCase):
    def test_extracts_raw_fenced_and_surrounding_objects(self):
        samples = ('{"answer": 1}', '```json\n{"answer": 1}\n```', 'Result: {"answer": 1} Thanks.')
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual({"answer": 1}, extract_json_object(sample))
    def test_rejects_non_object_json(self):
        with self.assertRaises(JsonOutputError):
            extract_json_object('[{"answer": 1}]')
    def test_requests_exactly_one_correction(self):
        provider = RecordingProvider(["bad", '{"answer": 2}'])
        result = run_json_prompt(provider, "question", cwd=Path.cwd(), validator=require_answer)
        self.assertTrue(result.succeeded)
        self.assertEqual(2, result.value)
        self.assertEqual(2, len(provider.prompts))
        self.assertIn("Original request:\nquestion", provider.prompts[1])
    def test_second_invalid_response_returns_error(self):
        provider = RecordingProvider(["bad", "still bad"])
        result = run_json_prompt(provider, "question", cwd=Path.cwd(), validator=require_answer)
        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.error)
        self.assertEqual(2, len(result.provider_results))

if __name__ == "__main__":
    unittest.main()
