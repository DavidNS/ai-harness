# Stage 3: State And Artifact Ports

Goal: isolate persistence before porting real orchestration.

## Actions

- Define `StateStorePort` for authoritative run state operations.
- Define `ArtifactStorePort` for artifact reads, writes, checksums, listing, and
  snapshots.
- Define `RunIndexPort` or equivalent for listing active and completed runs.
- Implement in-memory adapters first.
- Implement file-backed adapters second.
- Do not split state/artifact transactions prematurely. Resume safety is more
  important than perfect storage decomposition at this stage.
- Avoid frontend reads of `.ai-harness` or v2 runtime directories. All
  inspection must go through queries.

## Checkpoint

- Unit tests prove state invariants through the port.
- Integration tests prove:
  - start creates state;
  - list returns active runs;
  - completion records terminal state;
  - resume validates the run id and persisted phase;
  - missing or malformed state fails closed.

## Exit Criteria

- v2 has its own persistence boundary and does not require CLI code to inspect
  artifact files directly.

## Agent Handoff

Preserve resume safety over storage elegance. If state and artifact operations
must remain coupled for atomicity, keep that coupling inside the backend
boundary.
