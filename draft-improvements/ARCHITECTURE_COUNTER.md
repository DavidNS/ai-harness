# Architecture

This repository is an AI coding harness. It is both a Python project and an
operating environment for agents that inspect code, choose a strategy, run
bounded phases, persist artifacts, recover from interruption, and produce
evidence for humans.

Architecture is good here when it makes the harness easier to operate safely by
both humans and machines. A smaller file is only better when it clarifies
ownership, reduces context load, and makes validation more local.

## Purpose

The harness should turn a user request into a recoverable, evidence-backed
pipeline run.

- Every phase must have a bounded responsibility.
- Every important decision must leave an artifact or state record.
- Every resumable step must be validated before it continues.
- Every agent should receive the smallest context that can answer its question.
- Durable rules belong in code, tests, schemas, scripts, or this document.
- Temporary plans, worker notes, and refactor history belong outside the root
  architecture document.

## Harness Lifecycle

The shared lifecycle prepares the run, chooses the strategy, executes one
strategy graph, then records the terminal outcome.

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

The state machine is authoritative. A phase may move only through allowed graph
transitions or to `FAILED`. Recovery must reload persisted state and validate
that the requested resume path still matches the selected graph.

## Strategy-Specific Pipelines

Full SDD is the default for medium and high-complexity code work:

```text
EXPLORE
PROPOSAL
SPEC
DESIGN
TASKS
TDD_LOOP
LEARNING
```

The full-SDD split is intentional:

- `EXPLORE` gathers facts and constraints without committing to a solution.
- `PROPOSAL` names viable approaches and tradeoffs.
- `SPEC` defines expected behavior and acceptance criteria.
- `DESIGN` chooses architecture, boundaries, sequencing, and refactor level.
- `TASKS` converts the design into executable implementation units.
- `TDD_LOOP` implements, tests, and repairs code against the task plan.
- `LEARNING` extracts durable knowledge from the run.

Simple implementation is for low-risk bounded changes that do not need the full
design pipeline. Investigation is for turning vague improvement requests into
bounded improvement artifacts:

```text
INVESTIGATION_INTAKE
INVESTIGATION_DISCOVERY
INVESTIGATION_DECISION
INVESTIGATION_ARTIFACT
INVESTIGATION_REVIEW
```

Investigation phases must not silently become implementation. They produce
reviewed artifacts that can later feed a code pipeline.

## Phase Responsibilities

Phases own local semantics, not the global execution loop.

- A phase definition declares its prompt, worker playbook, capability manifest,
  output artifact, and validator.
- A phase service builds the scoped inputs for one phase family and writes the
  expected artifact.
- Validators enforce output shape and repairable quality rules.
- Control outputs request user decisions or bounded escalations; they must not
  mutate state directly.

Design and implementation are separate responsibilities. Design decides the
shape of the change. Tasks make that decision executable. Implementation follows
the task contract and reports evidence when the contract is wrong.

## Ownership Boundaries

Organize code by reason to change.

- Orchestration owns sequencing, control flow, phase dispatch, and final run
  outcomes.
- Pipeline graphs own legal phase order for each strategy.
- Phase services own bounded phase input construction, invocation, validation,
  and artifact writes.
- Stores own persistence, resume validation, mutable state invariants, and
  checksums.
- Providers own external process invocation and provider-specific execution
  mechanics.
- Artifacts own filesystem layout and run snapshots.
- Publishers own formatting and publication of durable outputs.
- Validators own schema and quality checks for candidate phase outputs.
- Launcher and UI code own command parsing, rendering, and operator interaction.

Reject boundaries that only move lines. Thin delegators, vague utility modules,
and helpers that receive an entire controller object usually hide coupling
instead of reducing it.

## Artifacts, State, And Recovery

Artifacts are the harness memory. State is the harness control surface.

- State records the run identity, selected strategy, current phase, completed
  phases, pending decisions, tasks, status, provider selection, and artifacts.
- Artifacts record phase outputs, decision requests and answers, worker job
  evidence, archive metadata, and snapshots.
- Resume must validate the run ID, graph position, pending decision, provider
  configuration, and phase preconditions before continuing.
- Archive must preserve enough state and artifacts for later inspection.
- Terminal cleanup must not destroy evidence required to understand the run.

Hidden side effects are architectural debt. If a service mutates state or
writes an artifact, that responsibility should be visible from its name,
constructor dependencies, or call site.

## Agent Legibility

The repository should be readable in bounded slices.

- Prefer explicit dependencies over broad parent objects.
- Prefer explicit return values over hidden cross-service mutation.
- Prefer stable phase names, artifact names, and schema keys over prose-only
  conventions.
- Route only the files, artifacts, and instructions needed for the current
  phase.
- Require evidence for architectural claims: file references, test output,
  artifact paths, or observed behavior.
- Let workers report uncertainty, contested assumptions, and scope expansion
  instead of forcing a confident answer.

Good agent architecture is not maximum autonomy. It is bounded autonomy with
recoverable state, inspectable artifacts, and cheap validation.

## Refactor Policy

A refactor is acceptable when it improves ownership without changing behavior
unless the behavior change was explicitly approved.

Use this ranking when design detects structural pressure:

```text
0. NONE
1. LOCAL_CLEANUP
2. STRUCTURAL_REFACTOR
3. ARCHITECTURAL_CHANGE
4. SEPARATE_INITIATIVE
```

Refactor inside the current task only when the implementation would otherwise
make the boundary worse. Split a separate initiative when the cleanup is useful
but not required for the current behavior.

Every refactor step should name:

- the boundary being improved;
- the behavior expected to remain unchanged;
- the files allowed to change;
- the focused validation command;
- the remaining risk or deferred cleanup.

Line count is a signal, not a goal. The real goal is lower context load, clearer
dependency direction, more auditable mutation, and better validation locality.

## Executable Guardrails

Architecture rules should become executable when they are stable.

- The state machine fails closed on illegal graph transitions.
- Phase validators reject malformed or low-value outputs before publication.
- Store APIs centralize state mutation and resume checks.
- Tests cover strategy selection, dispatch, recovery, control outputs, phase
  contracts, and investigation behavior.
- `scripts/check_architecture.py` checks graph coverage, dispatcher coverage,
  phase resources, import boundaries, state mutation paths, line budgets, and
  coupling warnings.

Warnings are acceptable while a boundary is being migrated, but they should be
named and tracked. Repeated review comments should become tests, validators,
architecture checks, clearer worker instructions, or better error messages.

