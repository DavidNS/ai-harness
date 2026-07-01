# Evaluation Criteria

This document defines the criteria used to evaluate new migration files against
the target architecture described in `ARCHITECTURE.md` and
`migration-roadmap/frontend-backend-hexagonal-boundaries.md`.

Use these criteria to review migrated code, plans, and module boundaries. The
goal is not to check naming preferences. The goal is to verify that the new
implementation moves toward the intended harness architecture.

## Review Method

For each reviewed file or change, report:

- `pass`: the criterion is clearly satisfied.
- `partial`: the criterion is mostly satisfied, but there are gaps, ambiguity,
  or temporary migration compromises.
- `fail`: the criterion is violated.
- `not_applicable`: the criterion does not apply to the reviewed area.

Each non-`pass` result should include:

- the affected file and line or symbol when available;
- the concrete reason;
- whether the issue blocks the target architecture or is acceptable migration
  debt;
- the smallest reasonable correction.

Severity levels:

- `critical`: reverses or blocks the target architecture.
- `major`: creates coupling or behavior duplication that will be expensive to
  unwind.
- `minor`: local naming, organization, or clarity issue that does not change the
  architecture.

## Core Architectural Criteria

### 1. CLI and UI Are Frontends, Not the Backend

The CLI must be treated as a presentation surface over harness capabilities, not
as the owner of lifecycle behavior.

Pass signals:

- CLI code parses input, renders output, shows progress, submits decisions, and
  translates user intent into commands or queries.
- CLI code calls a host or backend application service instead of directly
  executing lifecycle internals.
- UI code follows the same conceptual contract as the CLI: actions become
  backend commands, and backend state/events become rendered views.

Fail signals:

- CLI modules decide SDD phase transitions, phase semantics, escalation rules,
  or authoritative run state.
- CLI modules call model providers, git, CI, state storage, knowledge storage,
  filesystem tools, or tool runners for backend work.
- New code describes or implements `CLI = backend` or `UI = the only frontend`.

Default severity: `critical` for lifecycle ownership violations, `major` for
direct adapter calls.

### 2. Backend Owns Application and Domain Behavior

The backend must own orchestration, phase transitions, contracts, validation,
state, escalation, knowledge flow, release coordination, and AI worker
boundaries.

Pass signals:

- Lifecycle behavior lives in backend application services and domain modules.
- Domain concepts such as runs, phases, decisions, contracts, knowledge patches,
  and release coordination are represented explicitly.
- Backend code is usable without a terminal, browser, or HTTP server.

Fail signals:

- Phase logic is implemented in frontend, daemon API, adapter, or rendering
  code.
- Authoritative run/session state is owned by CLI/UI presentation state.
- Backend behavior requires terminal input/output, HTTP request objects, or UI
  state to function.

Default severity: `critical`.

### 3. Hosts Host the Backend; They Do Not Become the Backend

The local daemon/server and in-process runner are hosts or inbound adapters.
They may expose, wire, and manage the backend, but must not own business logic.

Pass signals:

- Hosts accept commands, expose queries, stream events, start/resume/cancel
  runs, inject user decisions, expose health/status, and wire ports to adapters.
- Both daemon and in-process hosts call the same backend application services.
- Process-level concerns such as long-running execution, cancellation,
  streaming, persistence wiring, and multi-client observation stay in hosts.

Fail signals:

- Daemon handlers decide phase semantics, implement SDD rules, or embed
  model-specific workflows.
- In-process and daemon hosts implement divergent lifecycle behavior.
- The daemon bypasses backend ports to access storage, git, models, tools, or
  CI directly for domain work.

Default severity: `critical` for business logic in hosts, `major` for duplicate
host behavior.

### 4. Hexagonal Dependencies Point Inward

Dependency direction must preserve the backend as the center and adapters as
outer implementations.

Required direction:

```text
frontends -> hosts -> backend/application -> backend/domain
backend/application -> backend/ports
adapters -> backend/ports
hosts wire backend ports to adapters
```

Pass signals:

- Backend application code depends on domain and ports.
- Adapters implement backend ports.
- Hosts perform composition/wiring.
- Frontends depend on command/query/event contracts or host APIs.

Fail signals:

- Backend imports frontend modules.
- Domain imports adapters.
- Domain imports host, daemon, HTTP, terminal, or UI modules.
- Adapters call back into frontend or own orchestration.
- Frontends import outbound adapters for backend work.

Default severity: `critical` for inward dependency violations.

### 5. External Capabilities Are Behind Ports

Concrete external capabilities must be isolated behind explicit backend ports.

Expected port categories include:

- model provider;
- git;
- CI;
- state store;
- knowledge store;
- tool runner;
- filesystem;
- event sink;
- user decision;
- clock.

Pass signals:

- Application services call ports, not concrete tools.
- Concrete implementations live in adapters.
- Tests can replace adapters with fakes or in-memory implementations.
- New external integration starts by defining or reusing a port.

Fail signals:

- Application/domain code shells out to git, model CLIs, CI tools, filesystem
  operations, or test runners directly.
- Storage implementation details leak into lifecycle logic.
- Event delivery is hardcoded to terminal output, WebSockets, or HTTP-specific
  primitives inside backend behavior.

Default severity: `major`, `critical` when the direct call controls lifecycle
state or phase semantics.

## Lifecycle Criteria

### 6. SDD Lifecycle Matches the Target Flow

The target local lifecycle is:

```text
EXPLORE
KNOWLEDGE_PHASE_EXTRACTOR
PROPOSAL
SPEC
DESIGN
TASKS
TDD_LOOP
KNOWLEDGE_PHASE_EXTRACTOR
```

The legacy phase names `IMPLEMENT`, `TEST`, `REVIEW`, and `ARCHIVE` may still
exist during migration, but new behavior should move toward `TDD_LOOP` and
knowledge extraction.

Pass signals:

- Phase ordering is explicit and inspectable.
- `EXPLORE` gathers context and does not make final proceed/reject decisions.
- `PROPOSAL` evaluates explored context and chooses proceed, reject,
  clarification, scope adjustment, or alternative approach.
- `SPEC`, `DESIGN`, and `TASKS` have separate responsibilities.
- `TDD_LOOP` groups test creation, implementation, review, and iteration.
- Knowledge extraction can happen after `EXPLORE` and after `TDD_LOOP`.

Fail signals:

- New code collapses exploration, proposal, design, implementation, and review
  into one opaque action.
- `EXPLORE` makes final approval/rejection decisions.
- Implementation bypasses test-first expectations where `TDD_LOOP` applies.
- Knowledge extraction is omitted from new lifecycle design.

Default severity: `major`, `critical` when phase ownership is placed outside
the backend.

### 7. TDD Loop Behavior Is Explicit

The implementation loop should follow test-driven behavior, not a loose
implement-then-test sequence.

Pass signals:

- The loop can create or identify tests that initially describe expected
  behavior.
- Implementation work is driven by those tests.
- Review checks that tests match behavior, code matches tests, and all required
  tests pass.
- The loop can iterate until approval or escalation.

Fail signals:

- Review is only a final formatting or lint step.
- Tests are optional even when behavior changes.
- The system cannot distinguish test creation, implementation, test execution,
  and review outcomes.

Default severity: `major`.

### 8. Escalation and User Decisions Are Domain Events

Any phase may escalate to a previous phase or request user input. This should be
represented as backend behavior and surfaced to frontends as events or decision
requests.

Pass signals:

- Escalations are explicit outcomes, not exceptions hidden in presentation code.
- User decision requests are generated by backend/application logic.
- Frontends render decision prompts and submit decisions back.
- Resuming after a decision uses the same run/session state model.

Fail signals:

- CLI prompts directly decide backend state transitions.
- Daemon or UI code encodes phase-specific escalation rules.
- Decision state is lost when a command exits or a client disconnects.

Default severity: `critical` for misplaced state transitions, `major` for weak
resume support.

## Knowledge Criteria

### 9. Learning Produces Knowledge Patches, Not Direct Truth Mutation

Knowledge learned during lifecycle execution must become candidate knowledge
patches first. It must not be written directly into the accepted source of
truth.

Pass signals:

- `KNOWLEDGE_PHASE_EXTRACTOR` creates permanent, versioned knowledge patch
  artifacts.
- Promotion from knowledge patch to source of truth is a separate workflow with
  validation and review.
- Candidate knowledge and accepted truth are represented separately.

Fail signals:

- New lifecycle code writes learned facts directly into SOT files.
- Promotion is implicit or indistinguishable from extraction.
- Knowledge artifacts are transient logs only.

Default severity: `critical`.

### 10. Knowledge Is Regenerative

Accepted source of truth must be able to regenerate both agent-oriented and
human-readable views.

Pass signals:

- Local agents DB is treated as derived from source of truth.
- Human knowledge files are treated as generated from source of truth.
- Deleting generated agent or human views does not destroy accepted knowledge.

Fail signals:

- The local agents DB is treated as the only authoritative knowledge store.
- Human documentation is manually edited as a separate truth source without a
  generation/promotional relationship.
- Generated views contain unique accepted facts not present in source of truth.

Default severity: `major`, `critical` when accepted knowledge would be lost.

## Release Criteria

### 11. Release Lifecycle Uses Trunk-Based Flow and CI Artifacts

The harness should connect local SDD work with branches, merge requests, CI
checks, and generated artifacts.

Pass signals:

- Main-branch artifacts can inform `EXPLORE`.
- Feature branches carry local SDD work.
- Feature CI and merge-request CI are treated as release lifecycle inputs.
- Main-branch CI regenerates status artifacts after merge.

Fail signals:

- Local lifecycle ignores available CI artifacts by design.
- Release behavior is hardcoded into frontend code.
- CI integration bypasses backend ports.

Default severity: `major`.

## Contract Criteria

### 12. Commands, Queries, and Events Are Explicit

Frontends and hosts should communicate through explicit command, query, and
event contracts.

Expected commands include concepts such as:

- `StartRun`;
- `ResumeRun`;
- `CancelRun`;
- `SubmitUserDecision`;
- `ApproveProposal`;
- `RejectProposal`;
- `PromoteKnowledgePatch`;
- `RetryPhase`.

Expected queries include concepts such as:

- `GetRun`;
- `ListRuns`;
- `GetRunState`;
- `GetPhaseDetails`;
- `GetKnowledgePatch`;
- `GetAvailableActions`.

Expected events include concepts such as:

- `RunStarted`;
- `PhaseStarted`;
- `PhaseCompleted`;
- `PhaseFailed`;
- `UserDecisionRequested`;
- `UserDecisionReceived`;
- `TestsStarted`;
- `TestsFinished`;
- `KnowledgePatchCreated`;
- `RunCompleted`;
- `RunCancelled`.

Pass signals:

- User intent is represented as commands.
- Read-only inspection is represented as queries.
- State changes and progress are represented as events.
- CLI and UI can share the same contract while rendering differently.

Fail signals:

- Frontends mutate backend state through ad hoc method calls with presentation
  concepts.
- Progress is only terminal text and cannot be consumed by other clients.
- Commands both mutate and render state in one coupled operation.

Default severity: `major`.

### 13. AI Worker Boundaries Are Small and Reproducible

AI steps should have one clear task and limited context. Deterministic code
should enforce structure, validation, state transitions, and repeatability.

Pass signals:

- AI worker invocations are phase/task scoped.
- Context passed to AI workers is intentionally bounded.
- Deterministic code validates worker outputs before state transitions.
- Prompts or worker contracts are inspectable and testable.

Fail signals:

- A single AI invocation owns broad multi-phase behavior.
- AI output directly mutates authoritative state without deterministic
  validation.
- Worker context is assembled from broad repository scans without phase-specific
  boundaries.

Default severity: `major`.

## Migration Criteria

### 14. Migration Follows the Clean Extraction Sequence

The preferred migration sequence is:

1. Identify orchestration and lifecycle logic mixed into CLI code.
2. Extract that logic into backend application services.
3. Define command/query/event contracts around runs and phases.
4. Define ports for model providers, git, CI, storage, filesystem, tools, and
   event output.
5. Make the CLI call the backend through an in-process host.
6. Add the daemon as a second host over the same backend.
7. Make the UI talk to the daemon.
8. Keep CLI support for both in-process and daemon-backed execution where useful.

Pass signals:

- New files move behavior inward before wrapping it in a daemon.
- Temporary compatibility layers are clearly identified.
- Extraction reduces CLI-owned orchestration.

Fail signals:

- The daemon is introduced first as a server wrapper around CLI-coupled logic.
- UI or daemon code duplicates lifecycle logic before backend extraction.
- Migration adds new direct adapter calls from CLI instead of defining ports.

Default severity: `major`, `critical` when the migration path reinforces the old
wrong boundary.

### 15. Module Boundaries Are Clear Even If Names Differ

The exact directory names may change, but each file should have a clear role:
frontend, host, backend application, backend domain, backend port, or adapter.

Pass signals:

- File placement and imports make the role obvious.
- Role-specific responsibilities match the architecture.
- Cross-boundary interactions happen through explicit contracts.

Fail signals:

- A module mixes rendering, orchestration, storage, and adapter implementation.
- A file cannot be assigned a single dominant architectural role.
- Naming suggests an architectural role that the code contradicts.

Default severity: `major`.

## Worker Report Template

Workers should summarize findings in this format:

```text
Reviewed scope:
- <files or directories>

Overall assessment:
- <aligned | partially aligned | misaligned>

Criteria results:
- <criterion number>: <pass | partial | fail | not_applicable> - <short reason>

Findings:
- [<severity>] <criterion number> <file:line or symbol>
  <concrete issue>
  Impact: <why it matters architecturally>
  Suggested correction: <smallest reasonable fix>

Open questions:
- <question or none>

Migration debt accepted:
- <debt item or none>
```
