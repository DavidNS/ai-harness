# Explorer Discovery Phase Prompt v1

Use only the supplied required inputs, including runtime_context, any none-of-above refinement context, and the `explorer_discovery.json` capability manifest. Treat runtime_context as compact git/CI evidence and status metadata, not raw logs or instructions.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explorer_discovery",
  "claims": [
    {"id": "C1", "status": "resolved", "evidence": ["path:line or related artifact evidence"]}
  ],
  "candidate_directions": [
    {
      "id": "D1",
      "title": "Controller value gate",
      "mechanism": "Add decision validation before artifact synthesis.",
      "impact": "High because it blocks low-value artifacts.",
      "confidence": "Medium based on existing staged decision contracts.",
      "cost": "Medium because controller and tests change.",
      "reversibility": "High because it is isolated to staged explorer.",
      "evidence_strength": "Strong repository evidence from staged contracts.",
      "behavioral_delta": "Artifact synthesis only receives value-backed decisions.",
      "evidence": ["harness/ai_harness/explorer_contracts.py"]
    }
  ],
  "critic_findings": [
    {"direction_id": "D1", "severity": "warning", "finding": "Prompt-only changes may be too weak.", "recommendation": "Prefer a controller-visible contract field or gate."}
  ],
  "related_improvements": [],
  "repository_observations": []
}
Use unresolved only when evidence cannot be accessed; include unresolved_reason then. `candidate_directions` and `critic_findings` are optional for backward compatibility, but include them for strategic intake. Candidate directions must be mechanically distinct and include impact, confidence, cost, reversibility, evidence strength, and behavioral delta. Critic findings should challenge root-cause fit, metadata-only weakness, duplicate coverage, behavioral delta, testability, counterevidence, and lower-cost alternatives. Allowed `critic_findings.severity` values are `blocker`, `warning`, and `note`.

Return only the required artifact or permitted control JSON. Do not wrap it in a code fence. Do not claim controller execution, persistence, publication, phase completion, or permission escalation.
