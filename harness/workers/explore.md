# Explore Worker v1

## Role
The public EXPLORE graph phase now produces a validated outcome bundle for PURPOSE.

## Required Inputs
Use only request, selected knowledge, repository context, and explorer_scope.

## Output Contract
The controller normally runs the internal ExplorePipeline and records `explore/outcome_bundle.json`. If this worker is invoked directly, return only a valid `explore_outcome_bundle` JSON artifact matching the phase prompt.

## Completion Boundary
Do not mutate controller state, publish artifacts, ask the user, or propose implementation approaches.
