# Architecture

This repository is an AI coding harness.

It must be readable for both software engineers and machines.

The harness is designed around small, explicit boundaries. A smaller file is only
better when it clarifies ownership, reduces context load, and makes validation
more local.

We split by domain to make boundaries clear, and we use hexagonal architecture to
increase isolation between orchestration, adapters, tools, storage, and user
interfaces.

We try to keep agent context as small and isolated as possible.

## Purpose

We are building a portable tool, as plug and play as possible, that automates the
full software engineering release lifecycle.

The tool includes a CLI and a UI.

The tool triggers pipelines composed of Python code, Codex/Claude, and git CI.

The harness orchestrates steps made up of deterministic code and AI workers. The
deterministic parts enforce structure, validation, state transitions, and
repeatability. The AI workers handle the nondeterministic parts that require
interpretation, exploration, judgment, or code generation.

We try to make the pipelines as reproducible as possible, so each AI step has one
clear task and one limited context.

## Three connected lifecycles

The harness architecture is made of three connected lifecycles:

- Local SDD lifecycle: the harness turns user intent into tested code through
  structured software design and development phases.
- Knowledge lifecycle: the harness captures reusable repository knowledge,
  stores candidate learning as patches, promotes accepted knowledge into a
  source of truth, and regenerates agent and human views from it.
- Release lifecycle: git branches and CI artifacts connect local harness work
  with trunk-based development.

One side of the system runs locally through the harness. The other side lives in
GitHub or GitLab through branches, merge requests, CI checks, and generated
artifacts.

## Local SDD lifecycle

The main phases of the software engineering lifecycle are based on current SDD
literature:

- `EXPLORE`, `PROPOSAL`, `SPEC`, `DESIGN`, `TASKS`, `IMPLEMENT`, `TEST`,
  `REVIEW`, `ARCHIVE`

The harness changes that flow in two important ways.

First, it replaces the simple implement-test-review sequence with a `TDD_LOOP`.

The `TDD_LOOP`:

- Creates the required test code. The tests should fail at first and describe
  the expected behavior.
- Creates the code that makes the tests pass.
- Reviews that all criteria are met: tests match the described behavior, code
  matches the tests, and all tests are green.
- Iterates until the reviewer approves or escalation is required.

Second, it extracts reusable knowledge after `EXPLORE` and after `TDD_LOOP`.

The ideal harness lifecycle is:

- `EXPLORE`, `KNOWLEDGE_PHASE_EXTRACTOR`, `PROPOSAL`, `SPEC`, `DESIGN`,
  `TASKS`, `TDD_LOOP`, `KNOWLEDGE_PHASE_EXTRACTOR`

The first extraction happens after `EXPLORE` because exploration may discover
reusable repository knowledge even if the initiative stops. The second
extraction happens after `TDD_LOOP` because approved code, tests, and behavior
provide stronger evidence that can be reused in future work.

Any phase can escalate a problem to a previous phase or ask the user if
something is unclear. For example, design may say not to touch a file, but
implementation may require it. Or an unexpected bug may appear. In that case,
the escalation process decides how to resolve it.

## Knowledge lifecycle

The learning system is not meant to create a project-management knowledge base
like Jira.

The goal is to create regenerative repository knowledge that helps agents
complete tasks with fewer tokens, fewer searches, and fewer iterations. The
system should store relevant information about repositories, code, flows,
domains, tests, errors, and current behavior.

This knowledge must also be useful for humans. The same accepted source of truth
should be able to produce human-readable files such as Markdown documentation,
domain descriptions, flow descriptions, interaction notes, design rationale, and
diagrams.

The learning system separates candidate knowledge from accepted truth:

- Source of truth (SOT): accepted knowledge that lives in git files.
- Knowledge patches (KP): candidate knowledge learned by the SDD flow during
  `KNOWLEDGE_PHASE_EXTRACTOR`.
- Local agents DB (LADB): a local agent-oriented database regenerated from the
  source of truth.
- Human knowledge files (HKF): human-readable documentation generated from the
  source of truth.

Knowledge learned during the lifecycle is not written directly into the source
of truth. Learning phases create permanent, versioned knowledge patches. A later
promotion pipeline, made of deterministic code and AI review, validates and
merges those patches into the source of truth when appropriate.

The regenerative knowledge flow is:

- `KNOWLEDGE_PHASE_EXTRACTOR` creates `KP` artifacts.
- `KP to SOT` promotes validated patches into the source of truth.
- `SOT to LADB` erases and repopulates the local agents DB from the source of
  truth.
- `SOT to HKF` generates human-readable knowledge files from the source of
  truth.

If the local agents DB is deleted, it should be possible to rebuild it from the
source of truth. If human knowledge files are deleted, it should be possible to
regenerate them from the source of truth.

## Release lifecycle

The release lifecycle follows trunk-based development and powers the SDD
lifecycle with artifacts generated by GitHub or GitLab CI.

The ideal release flow is:

- The main branch has generated artifacts that contain repository status
  information.
- A feature branch is created for the initiative.
- The local SDD lifecycle starts.
- `EXPLORE` uses main branch artifacts, if they exist, and extracts relevant
  repository status information from CI output artifacts.
- Later SDD phases use that information to make better decisions.
- At the end of SDD, the code is pushed to the feature branch.
- Push to feature triggers feature CI steps.
- A merge request to main is created, reviewed, and approved manually. It must
  pass the CI checks.
- When the merge request is merged to main, the CI pipeline creates new main
  artifacts.
- The loop repeats.

The real harness pipeline is therefore made of local SDD steps, regenerative
knowledge steps, and trunk-based release steps.

## SDD phase overview

Each SDD phase is not a single opaque action. Each phase is a bundle of smaller
steps with focused responsibilities, smaller context windows, and clearer
validation points.

### EXPLORE

Breaks down the user's initial intent and gathers the information needed to
understand the request. It does not make the final decision to proceed or reject;
it collects context for the next phases.

### PROPOSAL

Evaluates the gathered information and decides the next step: proceed, reject,
ask for clarification, take a different approach, or adjust the scope.

### SPEC

Turns the accepted proposal into a formal specification.

### DESIGN

Creates an implementation plan based on the specification.

### TASKS

Splits the plan into smaller tasks that can be executed sequentially or in
parallel. Each task clearly defines the steps needed to complete the
implementation.

### TDD_LOOP

Implements the tasks following a Test-Driven Development workflow.

## Full overview

- CLI + UI activate the harness lifecycle.
- Python harness code, Codex/Claude, and git CI execute the lifecycle.
- Local SDD phases turn user intent into tested code.
- Knowledge extraction creates versioned candidate patches.
- Validated knowledge patches are promoted into the source of truth.
- Agent and human knowledge views are regenerated from the source of truth.
- Trunk-based development and CI artifacts close the release loop.
