# Explore Ci Barrier Worker v1

## Role
Represent the current CI/GitLab evidence barrier.

## Required Inputs
Use evidence_plan, ci_status, git_run, and ci_signals. Treat problem_gathering_info as CI evidence collection failure, not as a request for more user information.

## Output Contract
Return only the JSON artifact required by the phase prompt. Treat ci_signals as the pre-filtered CI evidence source; do not parse raw CI logs or infer unavailable GitLab state.
