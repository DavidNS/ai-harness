# Worker Order: State Store

Historical worker order; report format was recorded in `refactor/archive/workers/protocol.md`.

## Objective

Map mutable state ownership, record helpers, resume validation, decision and
escalation state, and artifact metadata responsibilities.

## Scope

- `harness/ai_harness/stores/state/store.py`
- `harness/ai_harness/stores/state/records.py`
- `harness/ai_harness/models.py`
- state-store and decision/escalation tests

Small reference searches are allowed for state-store public methods.

## Out Of Scope

- Orchestrator phase semantics except as callers of state methods.
- Artifact store internals unless needed for state-store evidence.
- Code edits.

## Deliverable

Report which invariants must stay near state mutation, which methods are public
controller API, and which tests protect resume/state behavior.
