# Decision: Extract Run Progression and Terminalization

Date: 2026-06-28

Decision: select the runtime progression/terminalization boundary as the next
implementation step.

Evidence:
- `harness/ai_harness/orchestrator/lifecycle.py` held resume gating, graph
  advancement, waiting/impossible exits, and terminal snapshot/commit/cleanup
  ordering in one method group.
- Adjacent lifecycle concerns were already extracted into initializer,
  routing, resume-context, strategy persistence, and result helpers.
- Worker comparison found install/bootstrap tooling separable but less central
  to the orchestration refactor, while resume-loader coverage was a guardrail
  for this runtime boundary.

Constraints:
- Preserve terminal ordering:
  `prepare_completion -> snapshot_run -> commit_completion -> cleanup_run_temp -> clear_live`.
- Preserve waiting-run resume semantics and active-run decision rejection.
- Do not move StateStore mutation invariants, phase repair, worker/provider, or
  install/bootstrap behavior in this iteration.

Validation:
- `PYTHONPATH=harness python3 -B -m unittest tests.unit.test_resume_context_loader tests.integration.test_orchestrator tests.integration.test_recovery tests.integration.test_failures tests.integration.investigation.test_decisions tests.integration.test_launcher`
- `PYTHONPATH=harness python3 -B -m unittest discover tests`
