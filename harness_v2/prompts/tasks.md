# Prompt

Break the design into dependency-ordered pending implementation tasks. Each task should have a clear title, explicit dependencies, acceptance criteria, touched_paths, focused test commands, broader test commands, and pending status.

Reflect purpose/bundle.json implementation_mode in sequencing when it calls for local refactor, security work, existing functionality handling, or documentation-only work. Focused and broader tests must be command argument arrays, not shell strings. Keep tasks small enough for TDD execution and avoid broad touched_paths unless the design requires them.

Preserve purpose/bundle.json selected_entries and any target paths from the selected EXPLORE entries; for update_existing, include the target path in touched_paths or task acceptance criteria.
