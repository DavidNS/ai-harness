# v2 Context And Rules

## Migration Position

The migration is a parallel rebuild by capability, not a broad refactor of the
current implementation.

The current codebase has useful behavior and tests, but its main couplings are
too expensive to untangle in place:

- the CLI/backend boundary is process-plus-argv-plus-files;
- the CLI runtime reads `.ai-harness` artifacts directly;
- `Orchestrator` still owns broad lifecycle wiring through shared `RunContext`;
- state and artifact writes are tightly coupled to resume behavior;
- provider invocation, prompt assembly, artifact creation, control output
  parsing, and validation are still close together;
- git, CI, knowledge publication, and TDD execution are not yet behind narrow
  ports.

## Target Layout

Implementation package:

```text
harness_v2/
  backend/
    domain/
    application/
    ports/
  adapters/
    models/
    git/
    ci/
    storage/
    filesystem/
    tools/
  hosts/
    in_process/
    daemon/
  frontends/
    cli/
    ui/
```

Parallel test tree:

```text
test_v2/
  unit/
  integration/
  acceptance/
```

Dependency direction:

```text
frontends -> hosts -> backend/application -> backend/domain
backend/application -> backend/ports
adapters -> backend/ports
hosts wire backend ports to adapters
```

## Boundary Rules

- Domain code must not import hosts, frontends, or adapters.
- Application code may depend on domain and ports.
- Adapters implement ports and may depend on external systems.
- Hosts perform wiring and expose the backend to frontends.
- Frontends translate user intent into commands and render state/events.
- Frontends must not call model, git, CI, storage, filesystem, or tool adapters
  directly.

## Migration Strategy

Use an early cutover mindset.

The v1 implementation remains available as reference and fallback while v2 is
being built, but v2 does not need to preserve every v1 command, wrapper, flag,
or compatibility behavior at each step.

Important capabilities to preserve eventually:

- start a run;
- resume a run;
- list and inspect runs;
- ask for and receive user decisions;
- execute bounded AI worker tasks;
- persist state and artifacts reproducibly;
- run the SDD lifecycle;
- run the TDD loop;
- create and promote knowledge patches;
- coordinate release/git/CI signals;
- support CLI first, then daemon, then UI.

Do not introduce the daemon first. The daemon is a host, not the backend. The
backend application core must be usable in-process before it is exposed through
a local server.

## Migration Scope Boundaries

The v2 migration is responsible for architecture boundaries and deterministic
backend behavior, not for proving external-provider or production-security
properties.

In scope:

- keep side effects behind explicit backend ports and host wiring;
- make provider, repository, filesystem, storage, and tool boundaries visible;
- support fake, scripted, and fixture-backed tests that exercise backend flows;
- keep defaults fail-closed when a risky capability is not explicitly enabled;
- document where a boundary is intentionally coarse because an adapter cannot
  enforce a narrower contract yet.

Out of scope for this migration:

- granular sandbox/security design for real model providers beyond the current
  capability projection available in adapters;
- end-to-end tests that invoke real Codex, Claude, remote git, remote CI, or any
  other external service;
- guarantees that a real provider obeys `touched_paths` before the backend
  observes and validates the resulting diff;
- production hardening of provider workspaces, credentials, or OS-level
  isolation.

A migration stage may expose an opt-in capability for manual or later external
validation, but automated migration acceptance must not depend on real external
providers or networked services.

## Cross-Stage Checkpoints

Every stage must answer these questions before moving on:

- Does the new code preserve the dependency direction?
- Can the behavior be tested without a terminal, browser, daemon, real model, or
  real git remote?
- Are side effects behind ports?
- Is authoritative run state owned by backend/application/domain code?
- Are frontends only parsing input and rendering state/events?
- Can a failed or interrupted run be inspected and resumed safely?
- Are artifacts recorded through a backend-controlled contract?

If the answer is no, stop and fix the boundary before adding more features.

## Escalation Contract

Escalation is backend/application policy, not phase authority.

Phases, bundles, worker services, and subsystems report blocked work as a
descriptive escalation issue. They must not choose the lifecycle destination.

Use this split:

- detector: phase, bundle, TDD loop, worker validation, or adapter boundary;
- report: `EscalationIssue` with origin phase, category, reason, and evidence;
- policy: `EscalationPolicyService` resolves the issue to continue, ask the
  user, rewind, or fail;
- transition: orchestrator/application code updates authoritative run state and
  invalidates artifacts through backend ports.

User decisions follow the same rule. A decision answer may map to an escalation
category, but the pending decision and its effects do not carry a target phase.
Only the policy resolution may contain a target phase.

Examples:

- missing user/product context -> ask the user;
- missing or stale exploration evidence -> rewind to the appropriate discovery
  phase;
- requirements gap -> rewind to `SPEC_BUNDLE`;
- design gap -> rewind to `DESIGN_BUNDLE`;
- task plan gap -> rewind to `TASKS_BUNDLE`;
- contract or infrastructure failure -> fail closed unless a narrower recovery
  policy exists.

## Test Progression

```text
test_v2/unit
  domain transition tests
  DTO validation tests
  state invariant tests
  port contract tests with fakes

test_v2/integration
  in-process host tests
  file-backed state/artifact tests
  CLI v2 smoke tests
  provider fake/scripted tests
  resume and decision tests

test_v2/acceptance
  full fake-provider SDD flow
  full fixture-repo TDD flow
  knowledge patch creation
  daemon host smoke once daemon exists
```

Early stages should favor unit and integration tests. Acceptance tests become
useful once SDD and TDD flows are real.

## Architecture Guardrails For v2

Add v2 guardrails once the first real packages exist.

Required checks:

- `harness_v2/backend/domain` imports no adapters, hosts, or frontends.
- `harness_v2/backend/application` imports domain and ports only.
- `harness_v2/adapters` may import ports but not frontend modules.
- `harness_v2/hosts` may wire backend services to adapters.
- `harness_v2/frontends` may import host clients/contracts but not outbound
  adapters.
- no frontend reads v2 runtime artifact/state files directly;
- no provider adapter executes through shell strings;
- source files stay within agreed line budgets unless explicitly exempted.

## Things To Avoid

- Do not wrap the current v1 orchestrator in a daemon and call it architecture.
- Do not let CLI v2 read runtime files directly for status or decisions.
- Do not move every old file into `harness_v2/` and then refactor there.
- Do not implement daemon or UI before the in-process backend contract is
  stable.
- Do not split state/artifact persistence so aggressively that resume semantics
  become unclear.
- Do not make knowledge extraction part of the first walking skeleton.
- Do not let provider-specific permission shortcuts leak into application code.

## Definition Of Done For The Migration

The migration is complete when:

- `harness_v2` owns the backend application core, domain model, ports, adapters,
  hosts, and frontends;
- CLI and UI are frontends over the same backend behavior;
- daemon and in-process hosts call the same application services;
- SDD, TDD, knowledge, and release lifecycles run through explicit ports;
- authoritative run state is not managed by frontends;
- provider, git, CI, filesystem, storage, and tool side effects are adapters;
- tests cover domain, application, adapters, hosts, CLI, daemon, and acceptance
  flows;
- v1 can be archived or deleted without losing required product capabilities.
