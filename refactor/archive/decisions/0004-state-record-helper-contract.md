# Decision 0004: State Record Helper Contract Boundary

Date: 2026-06-28

## Decision

Use a narrow state record helper contract boundary instead of extracting
state-store mutation invariants. Add direct helper-level tests for control
record ID allocation and history publication while leaving `StateStore`
mutation, resume, decision, escalation, and completion behavior untouched.

## Rationale

Worker evidence showed `StateStore` invariants remain cohesive around
mutation/resume semantics and should not be split in this iteration. The stable
helper seam is `harness/ai_harness/stores/state/records.py`, which already owns
pure metadata, ID allocation, and history enumeration behavior. Direct tests
make that seam explicit without moving persistence-adjacent invariants away
from the mutation methods that enforce them.

Phase repair also remains deferred because generic contract repair is already
centralized and the remaining safe movement is only a low-value wrapper hoist.

## Constraints

- Do not edit `harness/ai_harness/stores/state/store.py`.
- Do not split decision, escalation, resume, or completion checks from
  `StateStore`.
- Do not touch orchestrator lifecycle, phase execution, provider, or gateway
  code.
- Keep this boundary test-only unless helper behavior itself needs correction.

## Validation

- `PYTHONPATH=harness python3 -B -m unittest tests.unit.test_state_records`
- `PYTHONPATH=harness python3 -B -m unittest tests.unit.test_models tests.unit.test_state_store tests.unit.test_state_records tests.integration.test_decision_gates tests.integration.test_recovery tests.integration.test_failures`
- `git diff --check`
