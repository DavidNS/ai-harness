# Worker Order: Orchestrator Lifecycle

Historical worker order; report format was recorded in `refactor/archive/workers/protocol.md`.

## Objective

Map the current ownership boundary for orchestrator lifecycle: initialization,
resume, execution loop, waiting/impossible/completed results, and finalization.

## Scope

- `harness/ai_harness/orchestrator/lifecycle.py`
- `harness/ai_harness/orchestrator/context.py`
- `harness/ai_harness/orchestrator/lifecycle_results.py`
- tests that directly reference lifecycle, resume, or orchestrator run behavior

Small reference searches are allowed for symbols defined in the scoped files.

## Out Of Scope

- Investigation publishing internals.
- Provider process mechanics.
- State store implementation details beyond calls made by lifecycle.
- Code edits.

## Deliverable

Report what lifecycle owns today, what it delegates, where it mutates run
context, and which responsibilities should remain in the orchestrator after the
second refactor.
