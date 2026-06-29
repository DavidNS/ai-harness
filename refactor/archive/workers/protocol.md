# Worker Protocol

Historical report format used by temporary refactor workers. This file is not a
startup instruction. Current lifecycle rules live in
`refactor/control/checkpoint.json`.

## Historical Rules

- Read only your order file and the files listed in its scope unless the order
  allows a small reference search.
- Do not edit files during mapping tasks.
- Do not infer architecture from vibes. Cite evidence.
- Do not ask to read the whole repo.
- If your scope is insufficient, report the missing file or question instead of
  expanding silently.
- If you discover an urgent behavior risk, report it clearly and stop short of
  broad cleanup.

## Historical Report Format

```text
Report status: completed | blocked | needs-decision

Boundary:
  Named boundary or checkpoint this report covers.

Allowed files:
  Files the worker was permitted to edit, or `none` for mapping-only work.

Changed files:
  Files actually changed, or `none`.

Finding:
  Concise summary of what this area owns today.

Evidence:
  File references and observed behavior. Include line numbers when available.

Dependencies:
  What this area calls, mutates, imports, or assumes.

Risks:
  What could break during refactor.

Validation:
  Focused tests or commands relevant to this boundary.

Validation result:
  passed | failed | not-run | pre-validation, plus a short reason when needed.

Recommendation:
  The next smallest useful action.

Remaining work:
  What still must happen before the boundary can be closed.

Durable lesson:
  The process rule, invariant, or guardrail this step should preserve.
```

## Historical Completion

Completed workers reported `work completed` to the orchestrator with this
format. The archived status index is retained as evidence only.
