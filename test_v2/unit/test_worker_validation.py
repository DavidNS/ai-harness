from __future__ import annotations

import unittest

from harness_v2.backend.application.worker_validation import WorkerOutputValidationResult, require_valid_worker_output


class WorkerOutputValidationTests(unittest.TestCase):
    def test_valid_result_allows_phase_advancement_boundary(self) -> None:
        result = WorkerOutputValidationResult(valid=True, schema_name="explore_bundle")

        require_valid_worker_output(result)

    def test_invalid_result_fails_before_phase_advancement(self) -> None:
        result = WorkerOutputValidationResult(valid=False, schema_name="explore_bundle", errors=("missing kind",))

        with self.assertRaises(ValueError):
            require_valid_worker_output(result)

    def test_validation_result_invariants_fail_closed(self) -> None:
        invalid_cases = (
            lambda: WorkerOutputValidationResult(valid=True, schema_name="explore", errors=("bad",)),
            lambda: WorkerOutputValidationResult(valid=False, schema_name="explore"),
            lambda: WorkerOutputValidationResult(valid=False, schema_name="", errors=("bad",)),
        )
        for create in invalid_cases:
            with self.subTest(create=create):
                with self.assertRaises((TypeError, ValueError)):
                    create()


if __name__ == "__main__":
    unittest.main()
