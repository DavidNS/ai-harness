# Stage 0 Companion: v1 Behavior Baseline

This document records the v1 behavior that matters before `harness_v2/` starts.
The current argv and file contracts are a reference baseline, not the target v2
API. v2 should rebuild the capabilities behind backend application contracts,
ports, adapters, and frontend commands.

## Capability Baseline

v2 must eventually replace these user-visible capabilities:

- Start a run from an inline request, prompt file, or stdin.
- Resume an unfinished run by run ID, with single-run inference where useful.
- Answer a waiting decision with free text or a selected option.
- Show repository harness status.
- List live, archived, and completed runs.
- Archive an unfinished run.
- Select or resolve a request route.
- Select a lifecycle flow or bundle.
- Run one bundle from artifacts produced by a previous run.
- Install CI templates.
- Install recommended packages.

Current public CLI examples are `aih "request"`, `aih --file request.md`,
`aih status`, `aih runs`, `aih resume [RUN_ID]`, `aih resume RUN_ID --answer
TEXT`, `aih resume RUN_ID --selected-option OPTION_ID`, `aih archive [RUN_ID]`,
`aih sdd`, `aih explore`, `aih proposal|spec|design|tasks|tdd RUN_ID`,
`aih install-ci [github|gitlab|both] [--force]`, and `aih install-packages
[GROUP...] [--all|--all-optional] [--dry-install]`.

The delegated backend argv used by v1 includes `harness/run.py --cwd ...`,
`--status`, `--show-runs`, `--resume`, `--archive`, `--install-ci`,
`--install-packages`, `--route`, `--flow`, `--from-run`, `--prompt-file`,
provider/model/reasoning/CI/branch flags, and request text over stdin.

Reference-only details that v2 should not treat as target API include backend
flag names and order, `--activated`, `--bypass`, `raw`, public `--file` versus
backend `--prompt-file`, `non-code` versus `non_code`, public package aliases
versus backend package flags, legacy `--answer-file`, source-bundle positional
run ID sugar, passthrough provider flags, and exact v1 exit codes such as
unfinished-run exit code `3`.

## Runtime And State Baseline

Runtime data is repository-local under `.ai-harness`. Artifacts live under
`.ai-harness/artifacts`.

Important paths:

- Live default: `.ai-harness/artifacts/current`
- Run-scoped live dir: `.ai-harness/artifacts/current-<run_id>`
- Completed or archived snapshots: `.ai-harness/artifacts/runs/<run_id>`
- Active pointer: `.ai-harness/artifacts/active.json`
- Live registry: `.ai-harness/artifacts/live-runs.json`
- Runtime lock: `.ai-harness/run.lock`

`ArtifactStore.for_run()` creates `current-<run_id>`, publishes `current` as a
compatibility symlink when possible, writes `active.json`, and records the run in
`live-runs.json`.

`active.json` has schema version `1`, the `run_id`, and the current live
directory name.

Artifact paths must be relative, non-empty, contained under the current artifact
directory, and must not include `..`. Symlink escapes are rejected. JSON artifacts
are UTF-8, sorted-key, two-space indented, and newline-terminated. A snapshot
fails if `.ai-harness/artifacts/runs/<run_id>` already exists.

The authoritative `state.json` shape is the Python runtime model, not only
`harness/schemas/state.schema.json`, because the schema may lag current strategy
values. The current model writes these top-level fields:

- `schema_version`
- `harness_version`
- `run_id`
- `user_input`
- `mode`
- `intent`
- `strategy`
- `complexity`
- `current_phase`
- `completed_phases`
- `failed_phases`
- `artifacts`
- `tasks`
- `selected_provider`
- `selected_provider_command`
- `selected_model`
- `status`
- `errors`
- `pending_decision`
- `timestamps`

`state.artifacts` is keyed by artifact path. Resume validation requires every
metadata `path` to match its key, every recorded file to exist, and every
checksum to match the recorded checksum.

Resume validation also requires the requested run ID to match persisted state,
`current_phase` to belong to the selected graph or be `FAILED`/`IMPOSSIBLE`,
`completed_phases` to be exactly a graph prefix, waiting runs to have a valid
pending decision, non-waiting runs to have no pending decision, and at most one
task to be `in_progress`, only during `TDD_BUNDLE`.

## Decisions And Recovery

Pending decision request artifacts use:

```text
decisions/<decision_id>/request.json
```

`state.pending_decision` contains `id`, `origin_phase`, `target_phase`,
`request_artifact`, and `created_at`. The request artifact path must match
`decisions/<decision_id>/request.json`.

Decision answers use:

```text
decisions/<decision_id>/answer.json
```

Direct CLI answers are allowed only with resume and only for waiting runs. The
direct answer payload has schema version `1`, kind `decision_answer`, the
pending `decision_id`, `answer`, and nullable `selected_option`.

`--status` is read-only and does not clean terminal live artifacts. It merges
registry entries, discovered live dirs, and snapshots, then prints run ID,
status, strategy, phase, pending decision ID, provider/model, artifact dir,
latest job evidence, and recovery commands for active or waiting runs.

`--show-runs` performs terminal live cleanup first, then renders live registry
entries, live states, and snapshots under `.ai-harness/artifacts/runs`.

Archive requires an unfinished run, validates resume first, writes
`archive.json`, snapshots recorded artifacts plus `archive.json`, clears the
live dir, and records status `archived`.

## Provider, Worker, And TDD Baseline

Provider CLI execution is an important safety boundary:

- Provider subprocesses use `shell=False`.
- Execution is bounded by timeout and output capture.
- stdout/stderr are streamed as progress and captured.
- Timed-out processes are killed.
- Environment projection is allowlist-based.

Worker permission projection accepts only one repo-wide `**` path rule in
`read` or `write` mode. Partial path permissions fail closed.

Claude projection permits file-oriented tools only and rejects worker command or
MCP allow-lists that it cannot enforce. Codex projection currently uses
`--dangerously-bypass-approvals-and-sandbox` and
`--dangerously-bypass-hook-trust` while rejecting worker commands and MCP tools.
This is a v1 risk to either preserve deliberately or redesign in v2.

Worker execution safety is split across capability manifests, worker playbooks,
provider projection, controller validation, and rollback. v2 should not treat
any one of those layers as sufficient by itself.

`WorkerGateway` builds bounded phase inputs, includes decision and escalation
history, loads the capability manifest, writes `jobs/<job_id>/request.json`,
passes manifest-derived permissions to the provider, writes
`jobs/<job_id>/result.json`, and parses validated control output.

The TDD loop processes at most one ready task at a time. Before each
implementation attempt, it snapshots repository files, symlinks, and directory
state while honoring repository ignore policy. After the worker returns, the
controller computes observed changed paths and repository diff, replacing
worker-claimed paths. Attempt artifacts are written before controller tests run.
Focused tests run before broader tests, and review runs only after passing
tests. Failed attempts restore the pre-attempt repository snapshot.

## Baseline Verification

Stage 0 baseline checks:

```bash
python3 -B scripts/check_architecture.py --summary
python3 -B -m unittest tests.unit.test_architecture_contracts tests.unit.test_backend_client tests.unit.test_console_runtime_primitives tests.unit.test_state_store tests.unit.test_runtime_lock tests.integration.test_launcher tests.integration.test_decision_gates
```

At the time this baseline was prepared, the architecture checker passed with
warnings, and the focused unit/integration baseline passed.

Useful existing coverage:

- CLI wrapper/backend argv: `tests/integration/test_root_launcher.py`,
  `tests/unit/test_backend_client.py`
- Status, runs, archive, recovery: `tests/integration/test_recovery.py`
- Decision answering: `tests/integration/test_decision_gates.py`
- Flow selection: `tests/integration/test_launcher.py`
- Install CI/packages: `tests/integration/test_launcher.py`,
  `tests/unit/test_recommended_packages.py`
- Artifact layout and snapshots: `tests/unit/test_artifact_store.py`
- State load, resume, and pending decisions: `tests/unit/test_state_store.py`
- Provider projection: `tests/integration/test_cli_provider.py`
- TDD snapshot and rollback: `tests/unit/test_tdd_loop.py`
- CLI/MVU separation and architecture guardrails:
  `tests/unit/test_architecture_contracts.py`
