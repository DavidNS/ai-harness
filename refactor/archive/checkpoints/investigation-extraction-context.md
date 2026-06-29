# Investigation Extraction Context Checkpoint

Checkpoint: C5 investigation extraction context boundary verified.

## Changed Boundary

`InvestigationExtractionContext` now owns the publication-time envelope used by
investigation knowledge synthesis and distill prompt construction. The existing
`InvestigationContext` remains discovery-derived and limited to related
improvements plus repository observations.

## Files Changed

- `harness/ai_harness/orchestrator/investigation_context.py`
- `harness/ai_harness/orchestrator/investigation_flow.py`
- `harness/ai_harness/orchestrator/investigation_distiller.py`
- `tests/unit/test_investigation_context.py`

## Validation

- `python3 -B -m unittest tests.unit.test_investigation_context tests.unit.test_investigation_distiller`
- `python3 -B -m unittest tests.integration.investigation.test_discovery tests.integration.investigation.test_review_and_outputs`
- `git diff --check`

## Remaining Work

- Architecture/document cleanup remains the next low-risk boundary.
- State-store invariant extraction remains deferred.
- Phase repair extraction remains deferred until a shared repair invocation
  service boundary is designed.
