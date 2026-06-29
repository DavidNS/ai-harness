# Worker Order: Worker Provider Boundary

Historical worker order; report format was recorded in `refactor/archive/workers/protocol.md`.

## Objective

Map worker invocation ownership: prompt construction, provider call mechanics,
job artifacts, permissions, debug snapshots, and compatibility helpers.

## Scope

- `harness/ai_harness/orchestrator/worker_exchange.py`
- `harness/ai_harness/orchestrator/worker_gateway.py`
- `harness/ai_harness/providers/base.py`
- `harness/ai_harness/providers/cli_provider.py`
- provider and worker invocation tests

Small reference searches are allowed for `WorkerGateway`, `_invoke`, and
provider `run_prompt` usage.

## Out Of Scope

- Phase semantics except inputs passed to workers.
- Investigation publishing.
- CLI UI rendering.
- Code edits.

## Deliverable

Report which responsibilities belong in a provider gateway, which belong in
phase/orchestrator code, and what compatibility constraints exist.
