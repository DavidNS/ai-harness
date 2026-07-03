# Prompt

Review whether the diff satisfies the task acceptance criteria, preserves scope, and is supported by red, focused, and broader validation evidence.

Return APPROVE only when the diff is within touched_paths, the focused/broader evidence supports the task, and acceptance criteria are met. Return REQUEST_CHANGES with concrete findings when evidence is missing, tests fail, the diff is out of scope, or the implementation does not satisfy the task. Include escalation_category only when the task plan, validation environment, or implementation scope is blocked rather than merely needing another attempt.
