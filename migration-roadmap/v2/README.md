# AI Harness v2 Migration

This folder contains the staged migration plan from the current harness to a
parallel v2 architecture.

The plan is split so an implementation agent can read the shared rules plus the
specific stage it is working on, instead of loading the full roadmap.

## Read Order

Every agent should read:

1. [00-context-and-rules.md](00-context-and-rules.md)
2. The current stage file from [stages](stages)

Architecture references:

- [../../ARCHITECTURE.md](../../ARCHITECTURE.md)
- [../frontend-backend-hexagonal-boundaries.md](../frontend-backend-hexagonal-boundaries.md)

## Stage Index

- [Stage 0: Baseline And Cut Line](stages/00-baseline-and-cut-line.md)
- [Stage 1: v2 Walking Skeleton](stages/01-walking-skeleton.md)
- [Stage 2: Domain Model For Runs, Phases, And Decisions](stages/02-domain-model.md)
- [Stage 3: State And Artifact Ports](stages/03-state-and-artifact-ports.md)
- [Stage 4: Application Services And Host Contract](stages/04-application-services-and-host-contract.md)
- [Stage 5: Provider Port And Worker Boundary](stages/05-provider-port-and-worker-boundary.md)
- [Stage 6: Minimal SDD Orchestration](stages/06-minimal-sdd-orchestration.md)
- [Stage 6.5: Explorer Workflow Skeleton](stages/06.5-explorer-workflow-skeleton.md)
- [Stage 7: User Decisions And Escalation](stages/07-user-decisions-and-escalation.md)
- [Stage 7.5: Explorer Decision Recovery](stages/07.5-explorer-decision-recovery.md)
- [Stage 8: TDD Loop Subsystem](stages/08-tdd-loop-subsystem.md)
- [Stage 9: Knowledge Lifecycle](stages/09-knowledge-lifecycle.md)
- [Stage 10: Release, Git, And CI Ports](stages/10-release-git-and-ci-ports.md)
- [Stage 11: Daemon Host](stages/11-daemon-host.md)
- [Stage 12: UI Frontend](stages/12-ui-frontend.md)
- [Stage 13: Cutover And v1 Retirement](stages/13-cutover-and-v1-retirement.md)

## Operating Rule

Migrate by capability, not by copying folders.

The v1 implementation is useful as reference, but v2 should establish clean
domain, application, host, frontend, port, and adapter boundaries from the
first executable slice.
