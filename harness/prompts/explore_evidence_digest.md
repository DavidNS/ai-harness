# Explore Evidence Digest Phase Prompt v1

Use only supplied inputs and the `explore_evidence_digest.json` capability manifest.

Return JSON only:
{
  "schema_version": 1,
  "phase": "explore_evidence_digest",
  "evidence": [
    {
      "id": "E1",
      "kind": "code",
      "claim": "Concrete repository-backed fact.",
      "status": "supported",
      "confidence": "high",
      "severity": "info",
      "sources": [{"type": "file", "path": "relative/path.py", "description": "Why this source matters"}]
    }
  ],
  "blockers": []
}

Allowed evidence kind: code, test, documentation, knowledge, ci, git, structure, security, scope, external.
Allowed status: supported, contradicted, partial, partially_supported, unresolved, not_applicable, blocked.
Allowed severity: info, warning, error, critical. Preserve controller_evidence facts unless they are irrelevant duplicates. Use blocked evidence for required information that is unavailable.
