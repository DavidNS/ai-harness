# Decision 0002: Investigation Extraction Context Boundary

Date: 2026-06-27

## Decision

Use `investigation context extraction` as the second implementation boundary after
the worker/provider checkpoint. Introduce an explicit extraction/publication
context object for knowledge synthesis and distill prompt payloads, while keeping
discovery context separate.

## Rationale

Worker evidence showed two behavior-sensitive candidates should remain deferred:
state-store invariants are cohesive around mutation/resume semantics, and phase
repair is still a cross-cutting invocation service concern. Architecture/document
cleanup is viable but mostly housekeeping. Investigation extraction context had a
clear seam, existing test coverage, and duplicated ad hoc payload assembly.

## Constraints

- Do not reopen the completed worker/provider boundary.
- Do not move repository observation gathering into this boundary.
- Preserve explicit repository evidence precedence and structured fallback
  behavior.
- Preserve downstream dict keys passed to knowledge synthesis and distill workers.

## Validation

- `python3 -B -m unittest tests.unit.test_investigation_context tests.unit.test_investigation_distiller`
- `python3 -B -m unittest tests.integration.investigation.test_discovery tests.integration.investigation.test_review_and_outputs`
- `git diff --check`
