# Explorer Review Phase Prompt v1

Use only the supplied required inputs and the `explorer_review.json` capability manifest.

Return # Review v1 Markdown only:
# Review v1
## Verdict
APPROVE
## Findings
State why the candidate is consistent with the decision and evidence.

Use REQUEST_CHANGES when the artifact has prose/contract/evidence issues. Mention decision/outcome drift explicitly in Findings. When value fields are present, also check that the artifact preserves the selected direction, value hypothesis, behavioral delta, rejected alternatives, counterevidence or falsifying conditions, and minimum verification, and that it does not resurrect critic-rejected directions.

Return only the required artifact or permitted control JSON. Do not wrap it in a code fence. Do not claim controller execution, persistence, publication, phase completion, or permission escalation.
