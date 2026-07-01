# Stage 4: Application Services And Host Contract

Goal: make commands and queries the stable interface to backend behavior.

## Actions

- Implement application services:
  - `StartRunService`;
  - `ResumeRunService`;
  - `CancelRunService`;
  - `SubmitUserDecisionService`;
  - `GetRunService`;
  - `ListRunsService`.
- Keep all state transitions inside application/domain logic.
- Keep host code limited to request handling, adapter wiring, and event
  delivery.
- Keep CLI code limited to parsing input and rendering command/query results.
- Replace host/application boundary responses that expose raw domain objects
  such as `RunRecord`, `RunStatus`, domain enums, or other domain aggregates
  with explicit serialization-stable DTOs.

## Checkpoint

- `InProcessHost` supports the command/query set above.
- CLI v2 uses the host contract, not subprocess argv or direct file reads.
- Tests can drive the backend without terminal or daemon code.

## Exit Criteria

- The backend application core is usable without a terminal, browser, or HTTP
  server.
- Host/backend command and query results do not expose raw domain aggregates,
  domain enums, or non-serializable domain objects.

## Agent Handoff

If a frontend needs data, add or refine a backend query. Do not let frontend
code inspect persistence files.
