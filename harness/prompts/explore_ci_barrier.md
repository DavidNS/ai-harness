# Explore Ci Barrier Phase Prompt v1

Use only the supplied required inputs and the `explore_ci_barrier.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explore_ci_barrier",
  "ci_requirement": "optional",
  "status": "ready",
  "evidence": [],
  "blockers": []
}

Set ci_requirement from evidence_plan. Use `ci_signals` as the normalized agent-ready CI baseline. Treat `problem_gathering_info` as evidence-source collection failure, not as a request for more user information. If ci_requirement is `required` and ci_signals.status is neither `ready` nor `partial`, return status `unavailable` with a blocker explaining the failed evidence source. If optional, include available ci_status/git_run/ci_signals provider facts when useful and do not block synthesis. If not_needed, status is `not_needed`. Do not ask the model to parse raw CI logs.
