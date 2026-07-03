# Prompt

Repair the target JSON artifact using only a structured JSON delta.

Return only JSON with this shape:
{
  "schema_version": 1,
  "kind": "json_artifact_delta",
  "target_artifact": "the target_artifact input value",
  "operations": [
    {"op": "add|replace|remove", "path": "JSON Pointer", "value": "required for add/replace"}
  ]
}

Use JSON Pointer paths. If current_artifact is null, create the whole artifact with one add operation at path "". Prefer the smallest operation list that fixes validation_error. Do not include prose or a code fence.
