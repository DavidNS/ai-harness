# Architecture

This document is a replacement candidate for the root architecture document. It is
not a history of the refactor. It is a map of how this harness is supposed to be
changed safely by humans and agents.

The harness is a recoverable AI coding pipeline. A request enters through the
launcher, gets routed to a strategy graph, executes bounded phases, persists
state and artifacts, and leaves evidence that a later process can inspect or
resume.

## Sources Of Truth

Do not infer architecture from prose when a source of truth exists.

| Concern | Source of truth | Change rule |
| --- | --- | --- |
| Phase names | `harness/ai_harness/contracts/enums.py` | Add a `PhaseName` before using a phase string anywhere else. |
| Strategy graph order | `harness/ai_harness/pipeline/*.py` | Graphs define legal lifecycle order. Do not bypass them in orchestration. |
| Transition legality | `harness/ai_harness/pipeline/state_machine.py` | All resume and progression behavior must validate against this. |
| Phase artifacts and validators | `harness/ai_harness/phases/registry.py` | Every worker phase must declare inputs, artifact, and validator here. |
| Phase dispatch | `harness/ai_harness/orchestrator/phase_execution.py` | Every graph phase that does work needs an explicit handler. |
| Run state | `harness/ai_harness/stores/state/store.py` | Mutate run state through the store, not scattered object writes. |
| Artifact layout | `harness/ai_harness/stores/artifact.py` | Write/read/snapshot run evidence through the artifact store. |
| Architecture gate | `scripts/check_architecture.py` | Stable rules belong here once they can be checked mechanically. |

A good architecture change updates all relevant sources of truth in the same
commit. A partial update is architectural drift.

## Runtime Shape

The normal control path is:

```text
harness/run.py
  -> ai_harness.launcher.*
  -> Orchestrator
  -> RunInitializer or resume loader
  -> RoutingCoordinator / StrategyPersister
  -> PhaseExecution
  -> phase services / task execution / investigation flow
  -> StateStore + ArtifactStore
  -> RunResult + terminal artifacts
```

The launcher owns CLI concerns only: argument parsing, status rendering,
resume/archive commands, provider configuration, and user-facing errors. It must
not own phase policy.

The orchestrator owns lifecycle concerns: initialization, routing, strategy
selection, phase progression, control-output handling, failure recording,
finalization, and result publication. It should coordinate collaborators rather
than becoming the place where every phase embeds its logic.

Providers own external execution. Provider code may know how to invoke `codex`,
`claude`, or another command. It should not know why a phase exists or how the
state graph works.

Stores own persistence and recovery. If a behavior changes what can be resumed,
archived, snapshotted, or audited, it is a store/state/artifact concern, not a
phase convenience.

## Strategy Graphs

All strategies share startup and terminal phases:

```text
INITIALIZING
LOADING_KNOWLEDGE
DETECTING_INTENT
ROUTING
SELECTING_STRATEGY
<strategy-specific phases>
FINALIZING
SNAPSHOTTING
COMPLETED
```

Full SDD is for medium or high-risk code work:

```text
EXPLORE
PROPOSAL
SPEC
DESIGN
TASKS
TDD_LOOP
LEARNING
```

The split is deliberate:

| Phase | Job | Must not do |
| --- | --- | --- |
| `EXPLORE` | Gather repo facts, constraints, unknowns, and analysis scope. | Choose final design or edit code. |
| `PROPOSAL` | Present viable approaches, scope, exclusions, and acceptance outline. | Pretend tradeoffs are settled without evidence. |
| `SPEC` | Define expected behavior and acceptance criteria. | Design internal boundaries. |
| `DESIGN` | Choose boundaries, invariants, implementation approach, test approach, and refactor level. | Emit executable task JSON or modify files. |
| `TASKS` | Convert spec and design into ordered implementation tasks with tests and source artifacts. | Re-decide architecture without escalation. |
| `TDD_LOOP` | Implement tasks, run tests, repair failures, and collect evidence. | Silently change the task contract. |
| `LEARNING` | Extract durable knowledge from the completed run. | Block a valid run because knowledge extraction failed. |

Investigation is not implementation. It turns vague improvement intent into a
reviewed improvement artifact:

```text
INVESTIGATION_INTAKE
INVESTIGATION_DISCOVERY
INVESTIGATION_DECISION
INVESTIGATION_ARTIFACT
INVESTIGATION_REVIEW
```

Investigation may produce future work. It must not silently edit code or pretend
that discovery is a completed implementation plan.

## Phase Contract

A phase is valid when these things agree:

1. `PhaseName` contains the phase string.
2. The selected strategy graph contains the phase in the right order.
3. `PhaseExecution` has a handler or explicit no-op for the phase.
4. `PHASE_DEFINITIONS` declares the worker-facing contract when a worker output
   is expected.
5. The phase writes the artifact declared by its phase definition.
6. The phase records artifacts in state when they become part of run evidence.
7. Tests cover the path or the architecture checker explains why it is allowed.

When adding or changing a phase, update the graph, registry, dispatcher, prompt,
worker playbook, capability manifest, validator, state tests, integration tests,
and architecture checker as applicable. If that list feels too large, the phase
is probably crossing too many concerns.

## Design Versus Implementation

This harness should protect the design/implementation boundary because agents
collapse it easily.

`DESIGN` should answer:

- Which boundary owns the change?
- What invariant must remain true?
- What refactor level is required: `NONE`, `LOCAL_CLEANUP`,
  `STRUCTURAL_REFACTOR`, `ARCHITECTURAL_CHANGE`, or `SEPARATE_INITIATIVE`?
- Which files or subsystems are in scope?
- Which tests prove the design was implemented correctly?
- What must be escalated back to `SPEC` or the user?

`TASKS` should answer:

- What is the smallest ordered implementation unit?
- Which source artifacts justify it?
- Which files are expected to change?
- Which focused and broader tests should run?
- Which deferrals are explicit and why?

`TDD_LOOP` should execute, not redesign. If implementation discovers that the
design is wrong, it should escalate or record the mismatch instead of smuggling
a different architecture into the diff.

## Ownership Boundaries

Prefer boundaries that can be explained by one reason to change.

| Boundary | Owns | Should not own |
| --- | --- | --- |
| `launcher` | CLI parsing, status, resume/archive rendering, provider flags. | Phase semantics or pipeline policy. |
| `orchestrator` | Run lifecycle, routing, phase sequencing, control output handling. | Provider process details or raw persistence formats. |
| `pipeline` | Strategy graphs and transition validation. | Phase implementation bodies. |
| `phases` | Worker contracts, validators, repairable output quality. | Run progression. |
| `stores` | State, artifacts, live registry, runtime locks, knowledge persistence. | Prompt construction or strategy choice. |
| `providers` | External model/process invocation and result projection. | Harness graph decisions. |
| `pipeline/tdd_loop` | Task execution, command evidence, implementation/test loop. | Full-SDD design decisions. |
| Investigation services | Intake/discovery/decision/artifact/review mechanics. | General orchestration or unrelated publishing. |

Bad boundaries move lines without reducing coupling. Warning signs:

- a helper takes an entire orchestrator/controller object;
- a module name says `utils`, `helpers`, or `common` but mixes policies;
- state mutation happens far away from validation;
- an implementation phase reads every previous artifact instead of scoped inputs;
- a new file has no single reason to change.

## State, Artifacts, And Recovery

Recovery is a core architecture requirement, not an afterthought.

State should answer:

- Which run is this?
- Which strategy and graph are active?
- Which phase is current?
- Which phases are complete?
- Is the run active, waiting, completed, failed, or archived?
- Is a user decision pending?
- Which artifacts are part of the run record?
- Which provider/model/command was selected?

Artifacts should answer:

- What did each phase produce?
- What did workers receive and return?
- What decision was requested and how was it answered?
- What command/test evidence exists?
- What was archived or snapshotted?

Resume must fail closed when the run ID, pending decision, selected strategy,
phase preconditions, or provider requirements do not match persisted state.
Cleanup must not delete evidence needed to debug or audit the run.

## Agent Operating Rules

Agents should be able to work from a bounded context slice.

- Read the source of truth first, then related implementation files.
- Ask workers for bounded investigations with file targets and evidence
  requirements.
- Prefer file references, command output, artifact paths, and tests over broad
  claims.
- Keep prompts and worker inputs scoped to the phase contract.
- Treat repeated mistakes as missing guardrails, not as reminders to be careful.
- Do not hide uncertainty. Escalation is better than confident architectural
  drift.

A machine-readable architecture is one where an agent can answer: what owns this,
what can change, what must not change, and what command proves it.

## Change Checklists

### Add A Full-SDD Phase

- Add the `PhaseName` enum value.
- Insert it into the intended strategy graph.
- Add a `PHASE_DEFINITIONS` entry if a worker output is produced.
- Add prompt, worker playbook, capability manifest, and validator.
- Add a `PhaseExecution` handler or explicit no-op.
- Add state-machine and dispatcher coverage tests.
- Update `scripts/check_architecture.py` allowlists only if the exception is a
  deliberate architecture decision.

### Change Phase Output Shape

- Update the phase definition and validator.
- Update prompt and worker instructions.
- Update all downstream consumers of the artifact.
- Add repair-path tests for malformed output.
- Preserve backward compatibility for resumable live runs or document why old
  runs cannot resume.

### Split A Large Module

- Name the boundary before moving code.
- Move one responsibility at a time.
- Keep behavior-preserving wrappers only temporarily.
- Add or keep focused tests around the extracted behavior.
- Run architecture checks and the smallest affected integration suite.
- Do not count the split as successful unless dependency direction is clearer.

### Add A Guardrail

- Prefer tests for behavior.
- Prefer validators for phase output contracts.
- Prefer `scripts/check_architecture.py` for structural repo rules.
- Prefer clearer errors when operators need to recover manually.
- Keep warnings non-blocking while a migration is active; turn them into errors
  when the repo is ready to enforce the rule.

## Refactor Policy

The design phase should classify refactor pressure explicitly:

```text
0. NONE
1. LOCAL_CLEANUP
2. STRUCTURAL_REFACTOR
3. ARCHITECTURAL_CHANGE
4. SEPARATE_INITIATIVE
```

Use the smallest refactor level that prevents the current change from making the
repo worse. Do not mix a valuable but unrelated cleanup into an implementation
unless the task cannot be completed safely without it.

A refactor is good when:

- ownership is easier to state;
- the caller reads less unrelated code;
- mutation is easier to audit;
- tests are more local or more meaningful;
- behavior is preserved unless explicitly changed;
- architecture warnings decrease or become more precise.

A refactor is bad when it only creates more files, introduces pass-through
wrappers, hides state mutation, duplicates policy, or makes future agents inspect
more places to understand one behavior.

## Executable Guardrails

Current guardrail stack:

- state-machine transition validation;
- phase output validators and repair attempts;
- task coverage validation for full SDD;
- state-store resume validation;
- architecture checker for graph, dispatcher, resource, import, mutation,
  budget, and coupling rules;
- unit/integration tests for strategy, routing, launcher, recovery,
  investigation, control outputs, and full SDD.

The architecture checker should remain readable and repo-native. Its JSON output
is for CI, dashboards, and future agents. Its text output is for humans.

The long-term rule is simple: if architecture matters enough to repeat in
review, it matters enough to encode as a test, validator, checker, or explicit
phase contract.
