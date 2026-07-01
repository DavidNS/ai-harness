# Frontend, Backend, and Local Harness Host

This draft clarifies the intended separation between frontends, the harness
backend, and a possible local daemon/server.

It describes the target architecture, not the current implementation.

## Core Idea

The CLI is not the backend.

The CLI and the UI are both frontends. They are different presentation surfaces
over the same harness capabilities:

- The CLI presents commands, prompts, progress, logs, and results in a terminal.
- The UI presents actions, state, progress, decisions, and results visually.

The backend is the harness application core: the orchestration and domain logic
that should behave the same no matter whether it is driven by CLI, UI, tests, or
automation.

The local daemon/server is not the backend itself. It is a host for the backend.
It exposes the backend to frontends through a local API.

In short:

```text
CLI and UI = frontends
Daemon/server = local host / inbound adapter
Application core = backend
Ports and adapters = explicit dependency boundaries
```

## Recommended Target Shape

The recommended ideal architecture is hybrid:

1. Build the harness backend as a clean in-process application core.
2. Make a local daemon the main host for real interactive usage.
3. Keep an in-process host for tests, scripts, simple commands, and bootstrap.

Conceptually:

```text
                    Frontends

        CLI                          UI
 command-driven MVU            visual MVU-style client
        |                           |
        | commands / queries        |
        | decisions / events        |
        v                           v

              Local Harness Host
       daemon API or in-process runner
                     |
                     v

              Backend Application Core
     lifecycle orchestration, state transitions,
     phase execution, escalation, knowledge flow
                     |
                     v

              Domain + Ports
     phases, contracts, run model, decisions,
     provider interfaces, storage interfaces
                     |
                     v

                  Adapters
     models, git, CI, filesystem, storage, tools
```

## Why a Local Daemon Fits the Ideal Architecture

The architecture document describes a harness that runs lifecycle pipelines,
coordinates deterministic code and AI workers, tracks state, extracts knowledge,
uses git/CI artifacts, and may ask the user for decisions during execution.

That kind of system benefits from a local daemon because it naturally needs:

- long-running runs;
- streaming events;
- pause, resume, and cancellation;
- stable run/session state;
- multiple clients observing the same execution;
- user decisions injected while a phase is running;
- observability for phase progress and failures;
- background work that can outlive a single CLI command;
- a shared API for both CLI and UI.

The daemon should not own business logic. It should host the application core,
manage process-level concerns, and expose a local protocol.

Good daemon responsibilities:

- accept commands from frontends;
- start, inspect, resume, and cancel runs;
- stream run events;
- persist and reload run state through backend ports;
- route user decisions back into blocked phases;
- expose health/status endpoints;
- enforce local process and permission boundaries.

Bad daemon responsibilities:

- deciding phase semantics;
- implementing SDD rules directly;
- embedding model-specific workflow logic;
- containing UI-specific presentation state;
- bypassing backend ports to access storage or tools directly.

## Backend Responsibilities

The backend is the application and domain layer. It should be usable without a
terminal, without a browser UI, and without an HTTP server.

It owns:

- SDD lifecycle orchestration;
- phase transitions;
- `EXPLORE`, `PROPOSAL`, `SPEC`, `DESIGN`, `TASKS`, `TDD_LOOP`, `REVIEW`,
  `ARCHIVE`, and knowledge extraction semantics;
- run/session state;
- phase contracts and validation;
- escalation rules;
- user-decision requests as domain/application events;
- knowledge patch creation and promotion workflows;
- release lifecycle coordination;
- deterministic validation steps;
- AI worker task boundaries;
- ports for external capabilities.

It should not own:

- CLI argument parsing;
- terminal rendering;
- browser layout;
- keyboard shortcuts;
- HTTP-specific request handling;
- WebSocket-specific framing;
- concrete filesystem, git, model, or CI implementation details.

## Frontend Responsibilities

Frontends translate user intent into backend commands and render backend state
or events.

The CLI frontend should use command-driven Model-View-Update:

```text
terminal input -> command -> backend effect -> events/state -> update -> view
```

The UI frontend can follow the same conceptual model:

```text
user action -> command -> backend effect -> events/state -> update -> view
```

Frontend responsibilities:

- parse user input;
- expose commands and options;
- render current state;
- render logs and progress;
- request missing user decisions;
- submit user decisions back to the backend;
- show errors and recovery options;
- manage presentation state.

Frontend non-responsibilities:

- deciding SDD lifecycle transitions;
- running phase internals;
- managing authoritative run state;
- calling model/git/storage/tool adapters directly;
- duplicating backend orchestration logic.

## Hexagonal Boundary

The backend should depend on ports, not concrete adapters.

Example ports:

- `ModelProviderPort`
- `GitPort`
- `CIPort`
- `StateStorePort`
- `KnowledgeStorePort`
- `ToolRunnerPort`
- `FilesystemPort`
- `EventSinkPort`
- `UserDecisionPort`
- `ClockPort`

Example adapters:

- Codex CLI adapter;
- Claude CLI adapter;
- Git command adapter;
- GitHub/GitLab CI adapter;
- local filesystem adapter;
- SQLite or file-backed state adapter;
- terminal event sink;
- WebSocket event sink;
- local daemon API adapter.

The important rule:

```text
Application core calls ports.
Adapters implement ports.
Frontends call commands/queries.
Frontends do not call outbound adapters directly.
```

## Command, Query, Event Model

The shared contract between frontends and the harness host should be explicit.

Commands ask the backend to do something:

- `StartRun`
- `ResumeRun`
- `CancelRun`
- `SubmitUserDecision`
- `ApproveProposal`
- `RejectProposal`
- `PromoteKnowledgePatch`
- `RetryPhase`

Queries ask for current information:

- `GetRun`
- `ListRuns`
- `GetRunState`
- `GetPhaseDetails`
- `GetKnowledgePatch`
- `GetAvailableActions`

Events report what happened:

- `RunStarted`
- `PhaseStarted`
- `PhaseCompleted`
- `PhaseFailed`
- `UserDecisionRequested`
- `UserDecisionReceived`
- `TestsStarted`
- `TestsFinished`
- `KnowledgePatchCreated`
- `RunCompleted`
- `RunCancelled`

This contract lets CLI and UI share the same backend behavior while rendering it
differently.

## Suggested Module Boundaries

One possible target structure:

```text
frontends/
  cli/
    commands/
    mvu/
    render/
  ui/
    app/
    state/
    components/

hosts/
  daemon/
    api/
    event_stream/
    process_lifecycle/
  in_process/
    runner.py

backend/
  application/
    use_cases/
    lifecycle/
    orchestration/
  domain/
    phases/
    runs/
    decisions/
    knowledge/
    release/
  ports/
    model_provider.py
    git.py
    ci.py
    state_store.py
    knowledge_store.py
    tool_runner.py
    event_sink.py

adapters/
  models/
  git/
  ci/
  storage/
  filesystem/
  tools/
```

The exact names can change, but the dependency direction should not:

```text
frontends -> hosts -> backend/application -> backend/domain
backend/application -> backend/ports
adapters -> backend/ports
hosts wire backend ports to adapters
```

The backend should not import frontend modules.

The domain should not import adapters.

The CLI should not call git, model providers, CI, state storage, or tool runners
directly unless it is implementing a frontend-only concern.

## In-Process Host vs Daemon Host

The in-process host is valuable and should remain part of the architecture.

Use it for:

- backend tests;
- integration tests;
- simple local commands;
- bootstrap flows;
- programmatic embedding;
- debugging without a daemon.

The daemon host should be the primary path for rich interactive usage.

Use it for:

- UI sessions;
- long-running CLI sessions;
- multi-client observation;
- streaming progress;
- resumable runs;
- cancellation;
- background execution;
- shared state between CLI and UI.

Both hosts should call the same backend application services.

## What This Means for FE/BE Separation

Do not define the split as:

```text
CLI = backend
UI = frontend
```

That split is misleading.

Use this instead:

```text
CLI = frontend
UI = frontend
daemon = local backend host
application core = backend
domain = backend model/rules
ports = backend dependency boundary
adapters = infrastructure implementations
```

This keeps the architecture aligned with:

```text
Dependencies are explicit at domain edges.
The backend uses hexagonal architecture to isolate orchestration from adapters,
tools, storage, and user interfaces.
The command frontend uses command-driven Model-View-Update so user intent,
state transitions, and backend effects stay separate and inspectable.
```

## Migration Principle

The clean migration path is not to introduce a daemon first.

The clean path is:

1. Identify orchestration and lifecycle logic currently mixed into CLI code.
2. Extract that logic into backend application services.
3. Define command/query/event contracts around runs and phases.
4. Define ports for model providers, git, CI, storage, filesystem, tools, and
   event output.
5. Make the CLI call the backend through an in-process host.
6. Add the daemon as a second host over the same backend.
7. Make the UI talk to the daemon.
8. Keep CLI support for both in-process and daemon-backed execution where useful.

This sequence avoids creating a server wrapper around code that is still
architecturally coupled to the CLI.

## Decision Summary

Recommended architecture:

```text
Hybrid local harness architecture.

Backend:
  application core + domain + ports.

Primary real-use host:
  local daemon/server.

Secondary host:
  in-process runner.

Frontends:
  CLI and UI, both command/event driven.

Infrastructure:
  adapters behind explicit ports.
```

The daemon is important for the ideal product experience, but the application
core is the real architectural center.
