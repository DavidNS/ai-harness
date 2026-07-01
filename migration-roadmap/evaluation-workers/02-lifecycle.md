# Worker 02: Lifecycle

## Mission

Evaluate whether the migrated files model the target SDD lifecycle, TDD loop,
escalation behavior, user decisions, and AI worker boundaries in the backend.

Canonical criteria:

- 6. SDD Lifecycle Matches the Target Flow
- 7. TDD Loop Behavior Is Explicit
- 8. Escalation and User Decisions Are Domain Events
- 13. AI Worker Boundaries Are Small and Reproducible

## Required Reading

- `ARCHITECTURE.md`
- `migration-roadmap/frontend-backend-hexagonal-boundaries.md`
- `migration-roadmap/evaluation-criteria.md`

## Recommended Scope

Review:

- `harness_v2/backend/domain/`
- `harness_v2/backend/application/`
- `harness_v2/hosts/`
- `harness_v2/frontends/cli/`
- lifecycle-related tests under `test_v2/`

## Prioritize Findings

Report issues where:

- `EXPLORE`, `PROPOSAL`, `SPEC`, `DESIGN`, `TASKS`, `TDD_LOOP`, or
  `KNOWLEDGE_PHASE_EXTRACTOR` responsibilities are collapsed into an opaque
  action;
- `EXPLORE` makes final proceed/reject decisions instead of gathering context;
- implementation/test/review flow bypasses the intended `TDD_LOOP`;
- escalation and user decision handling lives in CLI/UI/daemon presentation
  code instead of backend outcomes or events;
- AI worker invocations own broad multi-phase behavior or mutate authoritative
  state without deterministic validation.

## Ignore

- legacy phase names that remain only as compatibility placeholders;
- incomplete phase implementations when the new boundary makes the intended
  lifecycle explicit;
- lack of real AI provider integration if worker contracts and validation
  boundaries are represented.

## Output

Use the shared report format from
`migration-roadmap/evaluation-workers/README.md`.
