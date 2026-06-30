# Purpose Phase Prompt v1

Use only supplied inputs and the `purpose.json` capability manifest.

Return one of:
- a `purpose_bundle` JSON artifact;
- a `decision_request` control JSON object for user-facing choices;
- an `evidence_request` control JSON object when bounded additional EXPLORE evidence is required.

Normal JSON artifact:
{
  "schema_version": 1,
  "kind": "purpose_bundle",
  "summary": "Purpose summary.",
  "selected_entries": ["entry-1"],
  "implementation_mode": "direct_patch",
  "problem": "Problem to solve.",
  "scope": "Bounded implementation scope.",
  "approach": "Purpose-level approach, not low-level design.",
  "structural_work": [],
  "exclusions": ["Unrelated work."],
  "acceptance_outline": ["Observable acceptance expectation."],
  "evidence_refs": ["E1"]
}

Allowed implementation_mode: direct_patch, patch_with_local_refactor, refactor_first_then_patch, security_patch, existing_functionality, documentation_only, blocked.

Use EXPLORE evidence this way:
- If relevant structural_signals show the touched code is too coupled or over budget, choose patch_with_local_refactor or refactor_first_then_patch and put the incremental refactor in structural_work.
- If security_signals are directly relevant, choose security_patch.
- If evidence shows functionality already exists, choose existing_functionality.
- If critical evidence is missing and repository context could answer it, return evidence_request.
- If the missing answer is a product choice, return decision_request.

Control JSON objects must be the entire response, not fenced. For evidence_request use:
{
  "schema_version": 1,
  "kind": "evidence_request",
  "origin_phase": "PURPOSE",
  "reason": "Why more evidence is needed.",
  "questions": ["Specific evidence question."],
  "gatherers": ["code"],
  "scope_paths": ["optional/relative/path.py"]
}
