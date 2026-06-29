# Knowledge Review Phase Prompt v1

Use only the supplied controller inputs and the declared capability manifest. Return exactly one JSON object with:

- `schema_version`: exactly `1`
- `phase`: exactly `knowledge_review`
- `proposal_id`: matching the proposal under review
- `claim_reviews`: an array of claim review objects
- `relation_reviews`: optional array

Each claim review object must include `claim_id`, `decision`, and `reason`.
`decision` must be one of `accept`, `downgrade`, `reject_for_repair`, or `fail_review`.

Semantic policy:

- Review each active claim against accepted evidence and claim text.
- `accept` only when the claim is a durable repository fact.
- `downgrade` when wording is process-oriented, planning, speculative, or lacks durable proof.
- `reject_for_repair` when the claim can be salvaged by rewriting and include `suggested_text` with a concrete replacement.
- `fail_review` only for irreparable quality failure; keep claim unverified.

For `reject_for_repair`, `suggested_text` is required.
Use `suggested_text` in English with precise, repository-grounded wording and avoid adding run/process text.

Return only JSON, not Markdown or a code fence.
