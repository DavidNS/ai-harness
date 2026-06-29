# Worker Order: Investigation Flow

Historical worker order; report format was recorded in `refactor/archive/workers/protocol.md`.

## Objective

Map the investigation pipeline boundary: intake, discovery, decision, artifact,
review, publishing, learning proposal generation, and quality gates.

## Scope

- `harness/ai_harness/orchestrator/investigation_flow.py`
- `harness/ai_harness/orchestrator/investigation_bundle_parser.py`
- `harness/ai_harness/orchestrator/investigation_decision_reader.py`
- `harness/ai_harness/orchestrator/investigation_decisions.py`
- `harness/ai_harness/orchestrator/investigation_distiller.py`
- `harness/ai_harness/orchestrator/publishing.py`
- investigation-related tests

Small reference searches are allowed for symbols defined in the scoped files.

## Out Of Scope

- Non-investigation phase execution.
- Provider process mechanics.
- CLI UI.
- Code edits.

## Deliverable

Report the current sub-boundaries, hidden coupling back to orchestrator state,
quality/repair risks, and focused validation commands.
