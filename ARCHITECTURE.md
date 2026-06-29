# Architecture Principles

This repository is both a Python project and an operating context for agents.
Architecture decisions must make the code easier for humans and agents to
inspect, change, validate, and recover. A smaller file is only an improvement
when it reduces context load, clarifies ownership, and makes future changes
more local.

## Repository As Context

Agents do not learn from intent alone. They are steered by the repository they
see: file layout, names, tests, docs, lint rules, CI, scripts, errors, and
review comments. Treat those surfaces as part of the architecture.

- Keep stable engineering principles in this file.
- Keep temporary plans, task breakdowns, and investigation notes outside this
  file.
- Keep live refactor state, worker orders, decisions, and completed history in
  distinct docs so startup context stays small.
- Prefer executable guardrails over repeated human reminders.
- Make validation commands discoverable and cheap enough to run during normal
  work.
- Write docs that constrain future behavior, not docs that only narrate past
  cleanup.

## Ownership Boundaries

Organize code by responsibility, not by chronology or the shape of an old large
file. Every module should have one primary reason to change and a name that
makes that reason visible.

- Orchestration owns sequencing, control-flow decisions, phase transitions, and
  final run outcomes.
- Stores own persistence, checksums, resume validation, and mutable state
  invariants.
- Publishers own artifact formatting and publication details.
- Provider gateways own external process invocation, worker job artifacts, and
  provider-specific call mechanics.
- Phase services own bounded phase semantics; they should not own the global
  execution loop.
- UI modules own interaction and rendering; they should not contain domain
  policy.
- Pure parsing, projection, and classification helpers should stay stateless
  when behavior can be expressed without hidden mutation.

Reject boundaries that only move lines. Thin delegators, vague utility modules,
and helpers that receive an entire controller object usually hide coupling
instead of removing it.

## Agent Legibility

Design for bounded reading. A future worker should be able to inspect one
boundary, understand its dependencies, run focused validation, and report useful
evidence without loading the whole repository.

- Prefer explicit constructor dependencies over `__getattr__`, implicit parent
  mutation, or broad pass-through objects.
- Prefer explicit return values over hidden cross-service side effects.
- Keep state mutation easy to audit: the code that mutates an invariant should
  be close to the code that validates it.
- Route context intentionally. Do not dump the whole workspace into an agent
  when a scoped file set and a concrete question would do.
- Require evidence for architectural claims: file references, tests, failure
  output, or observed behavior.
- Allow workers and reviewers to push back when a request expands scope or
  conflicts with existing ownership.

## Feedback To Guardrails

Human attention is the scarce resource. If the same review comment, bug, or
agent mistake appears more than once, convert it into a durable guardrail.

Possible guardrails include:

- focused unit or integration tests;
- lint or type-check coverage;
- clearer architecture rules;
- worker instructions or review checklists;
- scripts that make the right validation path obvious;
- better error messages or artifact records.

Guardrails should be native to the repository where possible. Tests, lints,
types, docs, and scripts age better than opaque external process rules.

## Executable Architecture Checks

`scripts/check_architecture.py` is the repo-native architecture gate. It fails
closed on graph/dispatcher drift, phase resource drift, forbidden orchestrator
imports, and unauthorized state mutation paths. Size and coupling budgets are
reported as warnings first so cleanup pressure is visible without blocking
normal work until the boundary is ready to tighten.

## Refactor Acceptance

A refactor is acceptable when:

- the entrypoint is easier to read;
- the new boundary can be described in one sentence;
- dependency direction is clearer;
- state mutation is no less auditable than before;
- behavior is preserved unless a behavior change was explicitly approved;
- validation covers the changed responsibility.

A refactor is not acceptable when it only reduces line count, creates several
files with the same mixed responsibility, hides coupling behind pass-through
functions, or requires readers to reconstruct behavior from scattered side
effects.

Prefer small reversible steps. Each step should name the boundary, the intended
ownership improvement, the files allowed to change, and the validation command
that proves behavior still holds.
