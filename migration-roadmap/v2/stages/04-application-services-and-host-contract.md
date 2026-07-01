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

## Accepted Migration Debt

- `ClockPort` and a run-id generation port are not introduced in Stage 04.
  Application services use injected factories for deterministic tests; convert
  those factories into ports when broader infrastructure ports are introduced.
- Retry/retry-phase is intentionally not part of the Stage 04 public command
  contract. Add it only once failed phase state and retry semantics are modeled.
- Escalation is deferred to Stage 07. Stage 04 supports pending decisions and
  answer submission, but it does not choose escalation targets or invalidate
  later artifacts.
- Decision-request creation is backend/application behavior, not a frontend
  command. Future phase orchestration should emit `UserDecisionRequested` and
  persist waiting state through application services.


## Agent Handoff

If a frontend needs data, add or refine a backend query. Do not let frontend
code inspect persistence files.
