# Provider Permissions and Isolation

## Problem

Provider runs should not require repeated interactive approval for routine operations,
but they also must not receive unrestricted command or filesystem access. Codex
bounded execution currently fails closed because the adapter cannot yet enforce the
declared capability boundary.

The goal is not to force all sensitive actions through the orchestrator. A worker
that owns a phase may run the commands required by that phase, as long as the selected
provider can enforce the worker's command whitelist and filesystem boundary.

## Desired Direction

- Define provider-specific permission enforcement for Claude and Codex.
- Allow routine access within the target repository according to the active phase
  without repeated approval.
- Treat files inside the selected target repository as part of the user's chosen trust
  boundary.
- Deny access outside approved roots by default.
- Let the controller request explicit user approval for legitimate external knowledge,
  such as another repository or directory.
- Scope external grants to an exact path, access mode, and run unless the user
  explicitly chooses a broader lifetime.
- Require separate authority for external reads and external writes.
- Reuse an existing grant during its approved lifetime instead of asking repeatedly.
- Treat absolute paths, traversal, and symlinks resolving outside approved roots as
  external access.
- Keep commands deny-by-default and authorize only commands required by the active
  phase; undeclared commands require approval or fail closed.
- Support worker-run commands when the provider can enforce the phase whitelist.
- Keep orchestrator-owned bookkeeping, artifact persistence, approvals, and grant
  records outside worker control. Workers cannot broaden their own permissions.
- Fail closed when the selected provider cannot enforce the requested permissions.

## Target Worker Permissions

- `explore`, `proposal`, `spec`, `design`, `review`, and `learning` are read-only
  repository workers unless a future phase explicitly requires more.
- `implement` can read and write inside the selected target repository.
- `test` can read the repository and run only the test commands allowed for the
  active task. It must not receive edit/write authority merely because it can run
  tests.
- Harness artifacts are either written by the orchestrator or exposed through a
  narrowly scoped artifact path. Artifact writes must not imply broad repository
  write authority for read-only workers.

## Claude Enforcement Model

Claude should be projected through phase-specific tool sets:

- Read-only workers receive `Read`, `Glob`, and `Grep`.
- Implementation receives `Read`, `Glob`, `Grep`, `Edit`, and `Write`.
- Test workers receive `Read`, `Glob`, `Grep`, and `Bash`, but not `Edit` or
  `Write`.
- MCP tools remain denied unless a phase explicitly declares them.

Test command whitelisting must be enforced before Bash runs. Use Claude's native
Bash command restrictions when they are expressive enough for the required commands.
If native restrictions are not enough, run Bash through a harness-owned hook or
wrapper that validates the exact command or approved prefix before execution. If the
whitelist cannot be enforced, the worker invocation fails closed or asks for explicit
approval.

## Codex Enforcement Model

Codex does not use the same `Read`/`Bash`/`Edit` tool projection model as Claude.
For Codex, each worker should run with a phase-specific profile or temporary config
that combines:

- sandbox mode, such as read-only for exploration/review and workspace-write for
  implementation;
- writable roots limited to the target repository and any approved artifact/temp
  locations;
- command policy rules or approved command prefixes for the active phase;
- hooks that reject commands outside the worker's whitelist when policy rules are not
  expressive enough;
- restricted environment inheritance so secrets and unrelated user configuration are
  not exposed by default.

For example, the harness can launch Codex workers with separate profiles such as
`harness-explore`, `harness-implement`, `harness-test`, and `harness-review`. The
`harness-test` profile allows only the test commands declared for the active task and
will not grant repository write authority beyond what the sandbox requires for test
artifacts.

Codex support is possible, but it must be implemented as per-worker
profiles/policies/hooks rather than as Claude-style tool selection. If a Codex
version cannot enforce the requested whitelist and filesystem boundary, that worker
must fail closed.

## External Approval Display

Approval prompts for external access should disclose enough information for a useful
choice without printing full sensitive paths by default:

- show the requested operation, such as `read` or `write`;
- show whether the target is a file, directory, or symlink;
- show the basename and immediate parent directory;
- show a shortened resolved path, such as `~/.../other-project/config.yml`;
- include the worker phase and the requested grant lifetime;
- provide an explicit details/verbose path that reveals the full resolved path when
  the user needs it.

For example, a default prompt can say that the `test` worker requests `read` access to
`other-project/config.yml`, resolved as `~/.../other-project/config.yml`, for the
current run. Full absolute paths should still be recorded in controller-owned audit
state when needed, but they do not need to be printed in normal progress output.

## Remaining Implementation Questions

- What trusted command set is required for common languages and test runners?
- Which grant lifetimes should be supported beyond the default current-run scope?
