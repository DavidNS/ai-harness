# Worker Order: Phase Execution

Historical worker order; report format was recorded in `refactor/archive/workers/protocol.md`.

## Objective

Map phase dispatch, repair, validation exhaustion, task installation, and TDD
loop ownership.

## Scope

- `harness/ai_harness/orchestrator/phase_execution.py`
- `harness/ai_harness/orchestrator/phase_executor.py`
- `harness/ai_harness/phases/`
- tests that directly cover phase contracts, repair, or phase execution

Small reference searches are allowed for symbols defined in the scoped files.

## Out Of Scope

- Provider invocation internals.
- Investigation-specific publishing internals.
- Global lifecycle loop.
- Code edits.

## Deliverable

Report which logic is generic phase infrastructure versus phase-specific
semantics, and identify the safest split points.
