# Stage 9: Knowledge Lifecycle

Goal: add knowledge extraction after the core SDD/TDD behavior is reliable.

This stage implements the candidate-patch side of the knowledge lifecycle. It
does not implement the full regenerative pipeline yet.

## Actions

- Define `KnowledgeStorePort` or `KnowledgePatchStorePort` as a knowledge-domain
  boundary. Do not reuse the generic run `ArtifactStorePort` as the public
  knowledge contract.
- Implement knowledge patch creation.
- Keep candidate knowledge separate from accepted source of truth.
- Keep KP, SOT, local agents DB, and human knowledge files semantically
  distinct even if an adapter stores their bytes in the same physical storage
  backend.
- Defer promotion to its own later pipeline:
  - KP to SOT;
  - SOT to local agents DB;
  - SOT to human knowledge files.
- Do not let SDD learning write directly into accepted SOT.

## Out Of Scope

- Converting knowledge patches into SOT.
- Regenerating the local agents DB from SOT.
- Regenerating human knowledge files from SOT.
- Any workflow that treats candidate knowledge as accepted truth.

## Checkpoint

- Tests prove knowledge extraction creates versioned candidate patches.
- Tests prove rejected or malformed patches do not alter SOT.
- Regeneration flows are deterministic once SOT exists.

## Exit Criteria

- v2 supports knowledge extraction into versioned candidate patches without
  turning the knowledge subsystem into a generic project-management database.
- The port and storage model leave room for later KP-to-SOT and SOT-regeneration
  workflows without requiring them in this stage.

## Agent Handoff

Keep candidate knowledge and accepted knowledge separate. Learning phases create
patches; promotion into source of truth is a later validated workflow. For this
stage, the knowledge port should expose operations in domain terms such as
creating, listing, reading, validating, or rejecting knowledge patches. Promotion
operations may be designed as future extension points, but they are not required
for this stage. Raw artifact reads and writes may be adapter internals, but must
not become the application-facing knowledge API.
