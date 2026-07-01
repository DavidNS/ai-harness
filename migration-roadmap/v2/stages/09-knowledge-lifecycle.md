# Stage 9: Knowledge Lifecycle

Goal: add learning after the core SDD/TDD behavior is reliable.

## Actions

- Define `KnowledgeStorePort`.
- Implement knowledge patch creation first.
- Keep candidate knowledge separate from accepted source of truth.
- Add promotion later as its own pipeline:
  - KP to SOT;
  - SOT to local agents DB;
  - SOT to human knowledge files.
- Do not let SDD learning write directly into accepted SOT.

## Checkpoint

- Tests prove knowledge extraction creates versioned candidate patches.
- Tests prove rejected or malformed patches do not alter SOT.
- Regeneration flows are deterministic once SOT exists.

## Exit Criteria

- v2 supports the architecture's knowledge lifecycle without turning it into a
  generic project-management database.

## Agent Handoff

Keep candidate knowledge and accepted knowledge separate. Learning phases create
patches; promotion into source of truth is a later validated workflow.
