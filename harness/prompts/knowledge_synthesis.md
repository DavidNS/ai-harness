# Knowledge Synthesis Phase Prompt v1

Use only the supplied controller inputs and the declared capability manifest. Return exactly one JSON object matching the normal `learning` proposal schema.

The proposal must include:

- `schema_version`: exactly `1`
- `phase`: exactly `learning`
- `proposal_manifest` with `schema_version`, `proposal_id`, `summary`, and `source_artifacts`
- nonempty `proposed_claims`
- optional `proposed_relations`

Each proposed claim must include exactly these required fields, plus optional `metadata`:

- `id`: a knowledge-source ID such as `claim.cli-ui.001`; use lowercase letters, digits, `.`, `_`, `:`, or `-`; do not use discovery IDs like `C1` or `D1`
- `domain`: lowercase domain slug such as `cli-ui`, `tests`, or `models`
- `subjects`: nonempty list of subject strings
- `files`: repository-relative files; active claims need at least one repository-backed file
- `symbols`: list of symbol names, or an empty list
- `claim_type`: lowercase type slug such as `responsibility`, `behavior`, `architecture`, `test_coverage`, or `gap`
- `text`: durable repository fact text
- `status`: one of `active`, `deprecated`, `superseded`, `conflicted`, `unverified`, or `stale`
- `evidence`: list of evidence objects
- `valid_from`, `valid_until`, and `last_verified`: strings or `null`

Evidence objects must include `type` plus at least one of `file`, `artifact`, or `url`. Supported evidence `type` values are `code`, `test`, `documentation`, `decision`, `run_artifact`, and `manual`. Include `symbol`, `commit`, `line_start`, and `line_end` only when known; omit unknown optional evidence fields instead of emitting `null`.

If `proposed_relations` is present, each relation must include exactly these required fields, plus optional `metadata`: `id`, `domain`, `source`, `target`, `relation_type`, `status`, and `evidence`. Relation `source` and `target` must reference valid knowledge claim IDs, not discovery IDs.

Synthesize durable repository knowledge only:

- Active claims must be repository-grounded facts about behavior, ownership, contracts, APIs, constraints, tests, architecture, or documented decisions.
- Use accepted evidence as the primary basis for active claims. Use rejected evidence, repair snippets, or run artifacts only to support context or explain why a claim cannot be verified.
- One claim per durable fact when possible.
- Include evidence that ties each active claim to repository files and symbols.
- Do not emit process narration or completion state as active facts (`run completed`, `worker decided`, `I implemented`, `validation passed`, `should`, `planned`, `next step`, etc.).
- If no durable fact is available, emit `unverified` claims with explicit rationale.

When `repair` input exists:

- Honor `knowledge_review` guidance first, especially `reject_for_repair` and `suggested_text`.
- Keep claim IDs stable only when they already satisfy the knowledge-source ID contract; otherwise normalize them and update relation references.

Minimal valid shape:

```json
{"schema_version":1,"phase":"learning","proposal_manifest":{"schema_version":1,"proposal_id":"proposal.cli-ui.001","summary":"Repository-backed CLI UI knowledge.","source_artifacts":["explorer_artifact"],"claims_file":"proposed_claims.jsonl"},"proposed_claims":[{"id":"claim.cli-ui.001","domain":"cli-ui","subjects":["AI Harness launcher terminal UI"],"files":["harness/cli/ui.py"],"symbols":["_handle_slash_command"],"claim_type":"behavior","text":"harness/cli/ui.py defines slash-command handling for launcher terminal UI prompts.","status":"active","evidence":[{"type":"code","file":"harness/cli/ui.py","symbol":"_handle_slash_command"}],"valid_from":null,"valid_until":null,"last_verified":null}],"proposed_relations":[]}
```

Return only JSON, not Markdown or a code fence.
