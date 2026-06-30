"""CI template installation and git metadata support."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Literal

from .config import resource_path
from .errors import HarnessError
from .run_identity import run_id_date, run_id_token
from .stores.artifact import ArtifactStore
from .stores.state import StateStore

CI_TARGETS = ("github", "gitlab", "both")
BranchMode = Literal["off", "current", "create", "create-from-main"]

_TEMPLATE_VERSION = "1"
_GITHUB_TEMPLATE = resource_path("ci_templates", "github", "ai-harness-ci.yml")
_GITLAB_TEMPLATE = resource_path("ci_templates", "gitlab", ".gitlab-ci.yml")
_GITHUB_DESTINATION = Path(".github/workflows/ai-harness-ci.yml")
_GITLAB_DESTINATION = Path(".gitlab-ci.yml")
_MARKER = "ai-harness-ci-template:"


@dataclass(frozen=True, slots=True)
class InstallResult:
    installed: tuple[str, ...]
    skipped: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CiPreflight:
    ci_ok: bool
    ci_warnings: tuple[str, ...]
    signal_ok: bool
    signal_status: str
    signal_reason: str
    signal_warnings: tuple[str, ...]


def _run_git(repository: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _is_git_repository(repository: Path) -> bool:
    return _run_git(repository, ["rev-parse", "--is-inside-work-tree"]) == "true"


def _template_text(source: Path, provider: str) -> str:
    raw = source.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"# {_MARKER} provider={provider} version={_TEMPLATE_VERSION} sha256={digest}\n{raw}"


def _managed_digest(content: str) -> str | None:
    first = content.splitlines()[0] if content else ""
    match = re.search(rf"{re.escape(_MARKER)} .*sha256=([a-f0-9]{{64}})", first)
    return match.group(1) if match else None


def _expected_digest(source: Path) -> str:
    return hashlib.sha256(source.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _install_one(repository: Path, provider: str, *, force: bool) -> tuple[str | None, str | None, str | None]:
    if provider == "github":
        source, destination = _GITHUB_TEMPLATE, repository / _GITHUB_DESTINATION
    elif provider == "gitlab":
        source, destination = _GITLAB_TEMPLATE, repository / _GITLAB_DESTINATION
    else:
        raise ValueError(f"unsupported CI provider: {provider}")
    content = _template_text(source, provider)
    relative = str(destination.relative_to(repository))
    if destination.exists():
        existing = destination.read_text(encoding="utf-8", errors="ignore")
        if _managed_digest(existing) is None and not force:
            return None, relative, f"{relative} already exists and is not managed by ai-harness; use --force to replace it."
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return relative, None, None


def origin_url(repository: Path) -> str | None:
    return _run_git(repository, ["remote", "get-url", "origin"])


def infer_ci_target(repository: Path) -> str | None:
    url = (origin_url(repository) or "").casefold()
    if "github.com" in url:
        return "github"
    if "gitlab" in url:
        return "gitlab"
    if (repository / ".github").exists():
        return "github"
    if (repository / ".gitlab-ci.yml").exists():
        return "gitlab"
    return None


def install_ci_templates(repository: Path, target: str, *, force: bool = False) -> InstallResult:
    repository = repository.resolve()
    if target not in CI_TARGETS:
        raise HarnessError("ci target must be github, gitlab, or both")
    providers = ("github", "gitlab") if target == "both" else (target,)
    installed: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    for provider in providers:
        path, skip, warning = _install_one(repository, provider, force=force)
        if path:
            installed.append(path)
        if skip:
            skipped.append(skip)
        if warning:
            warnings.append(warning)
    return InstallResult(tuple(installed), tuple(skipped), tuple(warnings))


def _strip_git_suffix(value: str) -> str:
    return value[:-4] if value.endswith(".git") else value



def infer_github_project(origin: str | None) -> dict[str, str] | None:
    """Infer GitHub owner/repository metadata from a git remote URL."""
    if not origin:
        return None
    value = origin.strip()
    host = ""
    project = ""
    if value.startswith("git@") and ":" in value:
        host, project = value.removeprefix("git@").split(":", 1)
    elif value.startswith("ssh://") or value.startswith("http://") or value.startswith("https://"):
        parsed = urllib.parse.urlparse(value)
        host = parsed.hostname or ""
        project = parsed.path.lstrip("/")
    if host.casefold() != "github.com" or not project:
        return None
    project = _strip_git_suffix(project).strip("/")
    if project.count("/") < 1:
        return None
    owner, repo = project.split("/", 1)
    if not owner or not repo:
        return None
    return {
        "host": host,
        "project_path": f"{owner}/{repo}",
        "owner": owner,
        "repo": repo,
    }


def detected_ci_providers(repository: Path) -> tuple[str, ...]:
    repository = repository.resolve()
    detected: list[str] = []
    url = (origin_url(repository) or "").casefold()
    if "github.com" in url or (repository / ".github" / "workflows").is_dir():
        detected.append("github")
    if "gitlab" in url or (repository / ".gitlab-ci.yml").is_file():
        detected.append("gitlab")
    return tuple(dict.fromkeys(detected))


def _ci_unavailable(
    provider: str,
    reason: str,
    *,
    status: str = "unavailable",
    warnings: list[str] | None = None,
    scope: str = "unknown",
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "ai_harness_ci_signals",
        "provider": provider,
        "scope": scope,
        "status": status,
        "reason": reason,
        "base_ref": "",
        "base_sha": "",
        "head_ref": "",
        "head_sha": "",
        "run": {},
        "source": {},
        "warnings": list(warnings or []),
        "summary": {"status": status, "signal_count": 0},
        "path_index": [],
        "signals": [],
    }


def _run_plain_command(args: list[str], *, timeout: float = 15.0, runner: Callable[..., Any] = subprocess.run) -> subprocess.CompletedProcess[str]:
    return runner(args, capture_output=True, text=True, check=False, timeout=timeout)


def _json_from_command(args: list[str], *, runner: Callable[..., Any] = subprocess.run, timeout: float = 15.0) -> tuple[object | None, str | None]:
    try:
        completed = _run_plain_command(args, timeout=timeout, runner=runner)
    except Exception as exc:
        return None, str(exc)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "command failed").strip()
        return None, detail
    try:
        return json.loads(completed.stdout or "null"), None
    except json.JSONDecodeError as exc:
        return None, f"command returned malformed JSON: {exc}"


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _run_payload(source: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": source.get("run_id"),
        "run_attempt": source.get("run_attempt"),
        "workflow_name": source.get("workflow_name"),
        "url": source.get("run_url"),
        "event": source.get("event"),
        "created_at": source.get("created_at"),
        "conclusion": source.get("conclusion"),
        "status": source.get("status"),
        "pr_number": source.get("pr_number"),
    }


def _normalize_signal(item: object) -> dict[str, object] | None:
    if not isinstance(item, dict):
        return None
    return {
        "id": _text(item.get("id")),
        "tool": _text(item.get("tool")),
        "category": _text(item.get("category")),
        "severity": _text(item.get("severity")) or "warning",
        "status": _text(item.get("status")) or "unknown",
        "path": _text(item.get("path")),
        "summary": _text(item.get("summary")),
        "evidence": _text(item.get("evidence")),
        "confidence": _text(item.get("confidence")) or "medium",
        "agent_hint": _text(item.get("agent_hint")),
    }


def _signal_key(item: object) -> tuple[str, str, str, str]:
    if not isinstance(item, dict):
        return ("", "", "", "")
    return (
        _text(item.get("tool")),
        _text(item.get("category")),
        _text(item.get("path")),
        _text(item.get("summary")),
    )


def _normalize_path_index(path_index: object, signals: list[dict[str, object]]) -> list[dict[str, object]]:
    severities = {"error": 4, "critical": 4, "high": 3, "warning": 2, "medium": 2, "low": 1, "info": 0, "": 0}
    if isinstance(path_index, list) and all(isinstance(item, dict) for item in path_index):
        result: list[dict[str, object]] = []
        for item in path_index:
            path = _text(item.get("path"))
            if not path:
                continue
            result.append({
                "path": path,
                "signal_count": int(item.get("signal_count", 0)) if isinstance(item.get("signal_count"), int) else 0,
                "max_severity": _text(item.get("max_severity")) or "unknown",
            })
        return result
    counts: dict[str, dict[str, object]] = {}
    for signal in signals:
        path = _text(signal.get("path"))
        if not path:
            continue
        entry = counts.setdefault(path, {"path": path, "signal_count": 0, "max_severity": ""})
        entry["signal_count"] = int(entry["signal_count"]) + 1
        severity = _text(signal.get("severity"))
        if severities.get(severity, 0) > severities.get(_text(entry.get("max_severity")), 0):
            entry["max_severity"] = severity
    if counts:
        return [counts[path] for path in sorted(counts)]
    if isinstance(path_index, list):
        return [{"path": item, "signal_count": 0, "max_severity": "unknown"} for item in path_index if isinstance(item, str) and item]
    return []


def _normalize_signal_payload(
    provider: str,
    payload: dict[str, object],
    *,
    source: dict[str, object],
    scope: str = "trunk_baseline",
) -> dict[str, object]:
    raw_signals = payload.get("signals", []) if isinstance(payload.get("signals"), list) else []
    signals = [signal for item in raw_signals if (signal := _normalize_signal(item)) is not None]
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    ci_status = _text(summary.get("status")) or _text(payload.get("status")) or "unknown"
    base_ref = _text(payload.get("base_ref")) or _text(source.get("base_ref"))
    head_ref = _text(payload.get("head_ref")) or _text(source.get("head_ref")) or _text(source.get("ref"))
    head_sha = _text(payload.get("head_sha")) or _text(payload.get("commit")) or _text(source.get("head_sha")) or _text(source.get("run_sha"))
    base_sha = _text(payload.get("base_sha")) or _text(source.get("base_sha"))
    return {
        "schema_version": 2,
        "kind": "ai_harness_ci_signals",
        "provider": provider,
        "scope": scope,
        "status": "ready",
        "base_ref": base_ref,
        "base_sha": base_sha,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "run": _run_payload(source),
        "source": source,
        "warnings": list(payload.get("warnings", [])) if isinstance(payload.get("warnings"), list) else [],
        "summary": {**summary, "status": ci_status, "signal_count": len(signals)},
        "path_index": _normalize_path_index(payload.get("path_index", []), signals),
        "signals": signals,
        "raw_artifacts": payload.get("raw_artifacts", []),
    }


def _github_auth_problem(
    repository: Path,
    *,
    runner: Callable[..., Any],
    which: Callable[[str], str | None],
    scope: str,
) -> dict[str, object] | None:
    project = infer_github_project(origin_url(repository))
    if project is None and not (repository / ".github" / "workflows").is_dir():
        return _ci_unavailable("github", "no GitHub remote or workflow directory was detected", scope=scope)
    if which("gh") is None:
        return _ci_unavailable("github", "gh is not installed", status="problem_gathering_info", scope=scope)
    try:
        auth = _run_plain_command(["gh", "auth", "status"], timeout=8.0, runner=runner)
    except Exception as exc:
        return _ci_unavailable("github", f"gh auth status could not be checked: {exc}", status="problem_gathering_info", scope=scope)
    if auth.returncode != 0:
        detail = (auth.stderr or auth.stdout or "gh is not authenticated").strip()
        return _ci_unavailable("github", detail, status="problem_gathering_info", scope=scope)
    return None


def _github_project_path(repository: Path) -> str:
    project = infer_github_project(origin_url(repository))
    return project.get("project_path", "") if project else ""


def _github_run_source(repository: Path, run: dict[str, object], *, ref: str, scope: str) -> dict[str, object]:
    head_sha = run.get("headSha") or run.get("head_sha")
    return {
        "project_path": _github_project_path(repository),
        "scope": scope,
        "ref": ref,
        "base_ref": "main" if scope != "trunk_baseline" else "",
        "base_sha": _run_git(repository, ["rev-parse", "--verify", "origin/main"]) or "",
        "head_ref": ref,
        "head_sha": head_sha,
        "run_id": run.get("databaseId"),
        "run_url": run.get("url"),
        "workflow_name": run.get("workflowName"),
        "run_sha": head_sha,
        "conclusion": run.get("conclusion"),
        "status": run.get("status"),
        "event": run.get("event"),
        "created_at": run.get("createdAt"),
    }


def _download_github_signal_payload(
    run_id: object,
    *,
    runner: Callable[..., Any],
) -> tuple[dict[str, object] | None, str]:
    if run_id is None:
        return None, "GitHub Actions run did not include an id"
    with tempfile.TemporaryDirectory(prefix="ai-harness-gh-") as directory:
        try:
            download = _run_plain_command([
                "gh", "run", "download", str(run_id), "--name", "ai-harness-signals", "--dir", directory,
            ], timeout=20.0, runner=runner)
        except Exception as exc:
            download = subprocess.CompletedProcess([], 1, "", str(exc))
        if download.returncode != 0:
            return None, (download.stderr or download.stdout or "ai-harness-signals artifact was not found").strip()
        root = Path(directory)
        candidates = [root / "signals" / "ai-harness-signals.json", root / "ai-harness-signals.json"]
        candidates.extend(root.rglob("ai-harness-signals.json"))
        for candidate in candidates:
            if candidate.is_file():
                try:
                    payload = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    return payload, ""
        return None, "ai-harness-signals artifact did not contain signals/ai-harness-signals.json"


def github_ci_signals(
    repository: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    """Fetch latest main ai-harness CI signals from GitHub Actions when gh is configured."""
    unavailable = _github_auth_problem(repository, runner=runner, which=which, scope="trunk_baseline")
    if unavailable is not None:
        return unavailable
    run_fields = "databaseId,headSha,conclusion,status,workflowName,url,event,createdAt"
    runs, error = _json_from_command([
        "gh", "run", "list", "--branch", "main", "--status", "success", "--limit", "1", "--json", run_fields,
    ], runner=runner, timeout=12.0)
    if error:
        return _ci_unavailable("github", f"GitHub run list could not be fetched: {error}", status="problem_gathering_info", scope="trunk_baseline")
    if not isinstance(runs, list) or not runs:
        return _ci_unavailable("github", "no successful main GitHub Actions run was found", scope="trunk_baseline")
    run = runs[0]
    if not isinstance(run, dict):
        return _ci_unavailable("github", "latest GitHub Actions run response was malformed", status="problem_gathering_info", scope="trunk_baseline")
    source = _github_run_source(repository, run, ref="main", scope="trunk_baseline")
    payload, reason = _download_github_signal_payload(run.get("databaseId"), runner=runner)
    if payload is None:
        return {
            **_ci_unavailable("github", reason, status="partial", scope="trunk_baseline"),
            "source": source,
            "run": _run_payload(source),
            "head_ref": "main",
            "head_sha": _text(source.get("head_sha")),
        }
    normalized = _normalize_signal_payload("github", payload, source=source, scope="trunk_baseline")
    origin_main = _run_git(repository, ["rev-parse", "--verify", "origin/main"])
    warnings = list(normalized.get("warnings", [])) if isinstance(normalized.get("warnings", []), list) else []
    run_sha = _text(source.get("head_sha"))
    if origin_main and run_sha and origin_main != run_sha:
        warnings.append("Latest successful GitHub main workflow SHA does not match local origin/main.")
    normalized["warnings"] = warnings
    return normalized


def github_branch_ci_signals(
    repository: Path,
    branch: str,
    *,
    expected_head_sha: str = "",
    runner: Callable[..., Any] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    """Fetch the latest ai-harness CI artifact for a run branch or PR branch."""
    branch = branch.strip()
    if not branch:
        return _ci_unavailable("github", "run branch is unknown", scope="run_branch")
    unavailable = _github_auth_problem(repository, runner=runner, which=which, scope="run_branch")
    if unavailable is not None:
        return unavailable
    run_fields = "databaseId,headSha,conclusion,status,workflowName,url,event,createdAt,headBranch"
    runs, error = _json_from_command([
        "gh", "run", "list", "--branch", branch, "--limit", "10", "--json", run_fields,
    ], runner=runner, timeout=12.0)
    if error:
        return _ci_unavailable("github", f"GitHub branch run list could not be fetched: {error}", status="problem_gathering_info", scope="run_branch")
    if not isinstance(runs, list) or not runs:
        return _ci_unavailable("github", f"no GitHub Actions run was found for branch {branch}", scope="run_branch")
    candidates = [run for run in runs if isinstance(run, dict)]
    if expected_head_sha:
        exact = [run for run in candidates if _text(run.get("headSha")) == expected_head_sha]
        if exact:
            candidates = exact
    if not candidates:
        return _ci_unavailable("github", f"no GitHub Actions run matched branch {branch}", scope="run_branch")
    run = candidates[0]
    source = _github_run_source(repository, run, ref=branch, scope="run_branch")
    payload, reason = _download_github_signal_payload(run.get("databaseId"), runner=runner)
    if payload is None:
        return {
            **_ci_unavailable("github", reason, status="partial", scope="run_branch"),
            "source": source,
            "run": _run_payload(source),
            "head_ref": branch,
            "head_sha": _text(source.get("head_sha")),
        }
    normalized = _normalize_signal_payload("github", payload, source=source, scope="run_branch")
    warnings = list(normalized.get("warnings", [])) if isinstance(normalized.get("warnings", []), list) else []
    actual_head = _text(normalized.get("head_sha"))
    if expected_head_sha and actual_head and actual_head != expected_head_sha:
        warnings.append("GitHub branch workflow SHA does not match the local run branch HEAD.")
    normalized["warnings"] = warnings
    return normalized

def infer_gitlab_project(origin: str | None) -> dict[str, str] | None:
    """Infer GitLab API base URL and project path from a git remote URL."""
    if not origin:
        return None
    value = origin.strip()
    host = ""
    project = ""
    if value.startswith("git@") and ":" in value:
        host, project = value.removeprefix("git@").split(":", 1)
    elif value.startswith("ssh://") or value.startswith("http://") or value.startswith("https://"):
        parsed = urllib.parse.urlparse(value)
        host = parsed.hostname or ""
        project = parsed.path.lstrip("/")
    if not host or "gitlab" not in host.casefold() or not project:
        return None
    project = _strip_git_suffix(project).strip("/")
    if not project:
        return None
    scheme = "http" if value.startswith("http://") else "https"
    return {
        "api_url": f"{scheme}://{host}/api/v4",
        "host": host,
        "project_path": project,
        "project_id": urllib.parse.quote(project, safe=""),
    }


def _gitlab_json(url: str, token: str, *, timeout: float = 8.0) -> object:
    request = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _gitlab_bytes(url: str, token: str, *, timeout: float = 8.0) -> bytes:
    request = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _gitlab_unavailable(reason: str, *, provider: str = "gitlab", warnings: list[str] | None = None, status: str = "unavailable") -> dict[str, object]:
    return _ci_unavailable(provider, reason, status=status, warnings=warnings)


def gitlab_ci_signals(repository: Path, *, environment: dict[str, str] | None = None) -> dict[str, object]:
    """Fetch latest main ai-harness CI signals from GitLab artifacts when configured."""
    env = os.environ if environment is None else environment
    token = env.get("AI_HARNESS_GITLAB_TOKEN", "").strip()
    project = infer_gitlab_project(origin_url(repository))
    if project is None:
        return _gitlab_unavailable("origin remote is not a GitLab project", warnings=[])
    if not token:
        return _gitlab_unavailable("AI_HARNESS_GITLAB_TOKEN is not configured", status="problem_gathering_info")
    api_url = project["api_url"]
    project_id = project["project_id"]
    try:
        pipelines_url = (
            f"{api_url}/projects/{project_id}/pipelines?ref=main&status=success"
            "&order_by=id&sort=desc&per_page=1"
        )
        pipelines = _gitlab_json(pipelines_url, token)
        if not isinstance(pipelines, list) or not pipelines:
            return _gitlab_unavailable("no successful main pipeline was found")
        pipeline = pipelines[0]
        if not isinstance(pipeline, dict):
            return _gitlab_unavailable("latest main pipeline response was malformed")
        pipeline_id = pipeline.get("id")
        pipeline_sha = str(pipeline.get("sha", ""))
        jobs_url = f"{api_url}/projects/{project_id}/pipelines/{pipeline_id}/jobs?scope[]=success&per_page=100"
        jobs = _gitlab_json(jobs_url, token)
        if not isinstance(jobs, list):
            return _gitlab_unavailable("pipeline jobs response was malformed")
        job = next((item for item in jobs if isinstance(item, dict) and item.get("name") == "harness_quality"), None)
        if not isinstance(job, dict):
            return _gitlab_unavailable("harness_quality artifact job was not found")
        artifact_url = f"{api_url}/projects/{project_id}/jobs/{job.get('id')}/artifacts/signals/ai-harness-signals.json"
        payload = json.loads(_gitlab_bytes(artifact_url, token).decode("utf-8"))
        if not isinstance(payload, dict):
            return _gitlab_unavailable("ai-harness-signals artifact was malformed")
        source = {
            "api_url": api_url,
            "project_path": project["project_path"],
            "ref": "main",
            "head_ref": "main",
            "head_sha": pipeline_sha,
            "run_id": pipeline_id,
            "pipeline_id": pipeline_id,
            "pipeline_sha": pipeline_sha,
            "job_id": job.get("id"),
            "job_name": job.get("name"),
        }
        normalized = _normalize_signal_payload("gitlab", payload, source=source, scope="trunk_baseline")
        origin_main = _run_git(repository, ["rev-parse", "--verify", "origin/main"])
        warnings = list(normalized.get("warnings", [])) if isinstance(normalized.get("warnings", []), list) else []
        if origin_main and pipeline_sha and origin_main != pipeline_sha:
            warnings.append("Latest successful GitLab main pipeline SHA does not match local origin/main.")
        normalized["warnings"] = warnings
        return normalized
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return _gitlab_unavailable(f"GitLab CI signals could not be fetched: {exc}", status="problem_gathering_info")



def _provider_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "status": payload.get("status", "unavailable"),
        "reason": payload.get("reason", ""),
        "source": payload.get("source", {}),
        "summary": payload.get("summary", {}),
        "warnings": payload.get("warnings", []),
    }


def merged_ci_signals(repository: Path, *, environment: dict[str, str] | None = None) -> dict[str, object]:
    detected = detected_ci_providers(repository)
    if not detected:
        return {
            "schema_version": 2,
            "kind": "ai_harness_ci_signals",
            "status": "unavailable",
            "reason": "no CI provider was detected",
            "providers": {},
            "summary": {"status": "unavailable", "signal_count": 0, "provider_count": 0},
            "warnings": [],
            "path_index": [],
            "signals": [],
        }
    payloads: dict[str, dict[str, object]] = {}
    if "github" in detected:
        payloads["github"] = github_ci_signals(repository)
    if "gitlab" in detected:
        payloads["gitlab"] = gitlab_ci_signals(repository, environment=environment)
    signals: list[object] = []
    path_index: list[object] = []
    warnings: list[str] = []
    provider_statuses: dict[str, object] = {}
    for provider, payload in payloads.items():
        provider_statuses[provider] = _provider_summary(payload)
        if isinstance(payload.get("signals"), list):
            signals.extend(payload["signals"])
        if isinstance(payload.get("path_index"), list):
            path_index.extend(payload["path_index"])
        for warning in payload.get("warnings", []):
            if isinstance(warning, str):
                warnings.append(f"{provider}: {warning}")
    statuses = [str(payload.get("status", "")) for payload in payloads.values()]
    if any(status == "ready" for status in statuses):
        status = "ready"
    elif any(status == "partial" for status in statuses):
        status = "partial"
    elif any(status == "problem_gathering_info" for status in statuses):
        status = "problem_gathering_info"
    else:
        status = "unavailable"
    return {
        "schema_version": 2,
        "kind": "ai_harness_ci_signals",
        "status": status,
        "providers": provider_statuses,
        "summary": {"status": status, "signal_count": len(signals), "provider_count": len(provider_statuses)},
        "warnings": warnings,
        "path_index": path_index,
        "signals": signals,
    }

def _ci_files(repository: Path) -> list[Path]:
    files: list[Path] = []
    github = repository / ".github" / "workflows"
    if github.is_dir():
        files.extend(sorted(path for path in github.iterdir() if path.suffix in {".yml", ".yaml"} and path.is_file()))
    gitlab = repository / ".gitlab-ci.yml"
    if gitlab.is_file():
        files.append(gitlab)
    return files


def ci_status(repository: Path) -> dict[str, object]:
    repository = repository.resolve()
    files = _ci_files(repository)
    providers: list[dict[str, object]] = []
    warnings: list[str] = []
    if not files:
        warnings.append(
            "No CI pipeline is installed. CI lets the harness collect broader test evidence without installing large dependency sets locally; it is used for project verification context, not to collect personal data."
        )
    for path in files:
        relative = path.relative_to(repository).as_posix()
        provider = "gitlab" if relative == ".gitlab-ci.yml" else "github"
        content = path.read_text(encoding="utf-8", errors="ignore")
        managed = _managed_digest(content)
        template = _GITLAB_TEMPLATE if provider == "gitlab" else _GITHUB_TEMPLATE
        expected = _expected_digest(template)
        entry: dict[str, object] = {
            "provider": provider,
            "path": relative,
            "managed": managed is not None,
            "in_sync": managed == expected,
        }
        providers.append(entry)
        if managed is None:
            warnings.append(f"CI file {relative} exists but is not managed by ai-harness; no sync status is available.")
        elif managed != expected:
            warnings.append(f"CI file {relative} is managed by ai-harness but does not match the bundled template.")
    return {
        "schema_version": 1,
        "template_version": _TEMPLATE_VERSION,
        "providers": providers,
        "warnings": warnings,
    }


def ci_preflight(repository: Path, *, environment: dict[str, str] | None = None) -> CiPreflight:
    """Summarize startup CI checks for interactive launchers."""
    status = ci_status(repository)
    providers = status.get("providers") if isinstance(status.get("providers"), list) else []
    status_warnings = tuple(str(item) for item in status.get("warnings", []) if isinstance(item, str))
    ci_ok = bool(providers) and not status_warnings
    if not ci_ok:
        return CiPreflight(
            ci_ok=False,
            ci_warnings=status_warnings,
            signal_ok=False,
            signal_status="skipped",
            signal_reason="CI templates are missing or not managed by ai-harness.",
            signal_warnings=(),
        )
    signals = merged_ci_signals(repository, environment=environment)
    signal_status = str(signals.get("status", "unavailable"))
    signal_reason = str(signals.get("reason", ""))
    signal_warnings = tuple(str(item) for item in signals.get("warnings", []) if isinstance(item, str))
    return CiPreflight(
        ci_ok=True,
        ci_warnings=status_warnings,
        signal_ok=signal_status == "ready",
        signal_status=signal_status,
        signal_reason=signal_reason,
        signal_warnings=signal_warnings,
    )


def _dirty_excluding_harness_runtime(repository: Path) -> bool:
    status = _run_git(repository, ["status", "--porcelain", "--untracked-files=all"])
    if not status:
        return False
    for line in status.splitlines():
        path = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        path = path.strip('"')
        if not (path == ".ai-harness" or path.startswith(".ai-harness/")):
            return True
    return False


def git_metadata(repository: Path) -> dict[str, object]:
    repository = repository.resolve()
    if not _is_git_repository(repository):
        return {"schema_version": 1, "is_git_repository": False, "warnings": ["Repository is not a git worktree."]}
    dirty = _dirty_excluding_harness_runtime(repository)
    origin_main = _run_git(repository, ["rev-parse", "--verify", "origin/main"])
    warnings: list[str] = []
    if origin_main is None:
        warnings.append("origin/main is not available locally; remote sync freshness cannot be verified without fetching.")
    return {
        "schema_version": 1,
        "is_git_repository": True,
        "current_branch": _run_git(repository, ["branch", "--show-current"]) or "",
        "head": _run_git(repository, ["rev-parse", "HEAD"]),
        "origin_url": origin_url(repository),
        "origin_main": origin_main,
        "dirty": dirty,
        "warnings": warnings,
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:32] or "run"


def _run_branch_name(run_id: str, request: str) -> str:
    return f"aih/{run_id_date(run_id)}/{run_id_token(run_id)}-{_slug(request)}"


def _main_branch_ref(repository: Path) -> str | None:
    if _run_git(repository, ["rev-parse", "--verify", "main"]) is not None:
        return "main"
    if _run_git(repository, ["rev-parse", "--verify", "origin/main"]) is not None:
        return "origin/main"
    return None


def maybe_create_run_branch(repository: Path, run_id: str, request: str, mode: BranchMode) -> dict[str, object]:
    metadata = git_metadata(repository)
    metadata["branch_mode"] = mode
    metadata["created_branch"] = None
    if mode in {"off", "current"} or not metadata.get("is_git_repository"):
        return metadata
    warnings = list(metadata.get("warnings", []))
    if metadata.get("dirty"):
        warnings.append("Per-run git branch was skipped because the worktree has uncommitted changes.")
        metadata["warnings"] = warnings
        return metadata
    branch = _run_branch_name(run_id, request)
    base_ref = "HEAD"
    if mode == "create-from-main":
        base_ref = _main_branch_ref(repository) or ""
        if not base_ref:
            warnings.append("Per-run git branch was skipped because main or origin/main could not be resolved.")
            metadata["warnings"] = warnings
            return metadata
    metadata["branch_base_ref"] = base_ref
    checked_out = _run_git(repository, ["checkout", "-b", branch, base_ref])
    if checked_out is None:
        warnings.append(f"Per-run branch {branch} could not be checked out from {base_ref}.")
        metadata["warnings"] = warnings
        return metadata
    metadata["created_branch"] = branch
    metadata["current_branch"] = branch
    pushed = _run_git(repository, ["push", "-u", "origin", branch])
    if pushed is None:
        warnings.append(f"Per-run remote branch {branch} could not be pushed to origin.")
    metadata["warnings"] = warnings
    return metadata


def _ci_status_passed(payload: dict[str, object]) -> bool:
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    conclusion = _text(run.get("conclusion"))
    if conclusion:
        return conclusion == "success"
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    status = _text(summary.get("status"))
    return status in {"passed", "success"}


def compare_ci_signals(baseline: dict[str, object], branch: dict[str, object]) -> dict[str, object]:
    baseline_signals = baseline.get("signals", []) if isinstance(baseline.get("signals"), list) else []
    branch_signals = branch.get("signals", []) if isinstance(branch.get("signals"), list) else []
    baseline_by_key = {_signal_key(item): item for item in baseline_signals if _signal_key(item) != ("", "", "", "")}
    branch_by_key = {_signal_key(item): item for item in branch_signals if _signal_key(item) != ("", "", "", "")}
    classified: list[dict[str, object]] = []
    for key, signal in branch_by_key.items():
        if isinstance(signal, dict):
            classified.append({**signal, "status": "existing" if key in baseline_by_key else "new"})
    for key, signal in baseline_by_key.items():
        if key not in branch_by_key and isinstance(signal, dict):
            classified.append({**signal, "status": "resolved"})
    new_signals = [item for item in classified if item.get("status") == "new"]
    resolved_signals = [item for item in classified if item.get("status") == "resolved"]
    existing_signals = [item for item in classified if item.get("status") == "existing"]
    return {
        "schema_version": 1,
        "kind": "ai_harness_ci_comparison",
        "baseline": {
            "status": baseline.get("status"),
            "summary": baseline.get("summary", {}),
            "head_ref": baseline.get("head_ref"),
            "head_sha": baseline.get("head_sha"),
            "run": baseline.get("run", {}),
        },
        "branch": {
            "status": branch.get("status"),
            "summary": branch.get("summary", {}),
            "head_ref": branch.get("head_ref"),
            "head_sha": branch.get("head_sha"),
            "run": branch.get("run", {}),
        },
        "summary": {
            "new_signal_count": len(new_signals),
            "existing_signal_count": len(existing_signals),
            "resolved_signal_count": len(resolved_signals),
            "branch_passed": _ci_status_passed(branch),
        },
        "signals": classified,
    }


def record_branch_ci_artifacts(
    repository: Path,
    artifacts: ArtifactStore,
    state: StateStore,
    *,
    github_ci_mode: str,
    warnings: list[str],
) -> dict[str, object]:
    if github_ci_mode != "branch":
        return {"status": "skipped", "blockers": []}
    git = _safe_artifact_json(artifacts, "git-run.json")
    branch = _text(git.get("created_branch")) or _text(git.get("current_branch"))
    head = _run_git(repository, ["rev-parse", "HEAD"]) or _text(git.get("head"))
    blockers: list[str] = []
    if not branch:
        blockers.append("GitHub branch CI is required, but no run branch was created or detected.")
        branch_signals = _ci_unavailable("github", blockers[-1], scope="run_branch")
    else:
        branch_signals = github_branch_ci_signals(repository, branch, expected_head_sha=head)
    artifacts.write_json("ci/run-branch-signals.json", branch_signals)
    state.record_artifact("ci/run-branch-signals.json", "FINALIZING")
    baseline = _safe_artifact_json(artifacts, "ci-signals.json")
    comparison = compare_ci_signals(baseline, branch_signals)
    artifacts.write_json("ci/comparison.json", comparison)
    state.record_artifact("ci/comparison.json", "FINALIZING")
    for warning in branch_signals.get("warnings", []) if isinstance(branch_signals.get("warnings"), list) else []:
        if isinstance(warning, str):
            warnings.append(warning)
    status = _text(branch_signals.get("status"))
    if status != "ready":
        blockers.append(f"GitHub branch CI signals are {status or 'unavailable'}.")
    actual_head = _text(branch_signals.get("head_sha"))
    if head and actual_head and head != actual_head:
        blockers.append("GitHub branch CI artifact is stale for the local run branch HEAD.")
    if status == "ready" and not _ci_status_passed(branch_signals):
        blockers.append("GitHub branch CI did not pass.")
    return {
        "status": "blocked" if blockers else "passed",
        "blockers": blockers,
        "branch": branch,
        "head": head,
        "artifact": "ci/run-branch-signals.json",
        "comparison_artifact": "ci/comparison.json",
    }


def record_ci_and_git_artifacts(
    repository: Path,
    artifacts: ArtifactStore,
    state: StateStore,
    *,
    run_id: str,
    request: str,
    branch_mode: BranchMode,
    warnings: list[str],
    github_ci_mode: str = "baseline",
) -> None:
    ci = ci_status(repository)
    git = maybe_create_run_branch(repository, run_id, request, branch_mode)
    signals = _ci_unavailable("github", "GitHub baseline CI collection is disabled", scope="trunk_baseline") if github_ci_mode == "off" else merged_ci_signals(repository)
    signals = normalize_ci_signal_paths(repository, signals)
    artifacts.write_json("ci-status.json", ci)
    state.record_artifact("ci-status.json", "INITIALIZING")
    artifacts.write_json("git-run.json", git)
    state.record_artifact("git-run.json", "INITIALIZING")
    artifacts.write_json("ci-signals.json", signals)
    state.record_artifact("ci-signals.json", "INITIALIZING")
    signal_warnings = signals.get("warnings", []) if isinstance(signals, dict) else []
    for warning in [*ci.get("warnings", []), *git.get("warnings", []), *signal_warnings]:
        if isinstance(warning, str):
            warnings.append(warning)


def ci_observations_from_artifact(artifacts: ArtifactStore) -> list[dict[str, object]]:
    if not artifacts.exists("ci-status.json"):
        return []
    try:
        status = artifacts.read_json("ci-status.json")
    except Exception:
        return []
    if not isinstance(status, dict):
        return []
    observations: list[dict[str, object]] = []
    providers = status.get("providers")
    if isinstance(providers, list) and providers:
        for item in providers:
            if not isinstance(item, dict):
                continue
            observations.append({
                "kind": "ci",
                "path": str(item.get("path", "")),
                "provider": str(item.get("provider", "")),
                "managed": bool(item.get("managed")),
                "in_sync": bool(item.get("in_sync")),
            })
    else:
        observations.append({
            "kind": "ci",
            "path": "",
            "provider": "none",
            "managed": False,
            "in_sync": False,
            "matches": ["No CI pipeline is installed for this repository."],
        })
    signals = _safe_artifact_json(artifacts, "ci-signals.json")
    for item in signals.get("path_index", []) if isinstance(signals.get("path_index"), list) else []:
        if not isinstance(item, dict):
            continue
        raw_path = _text(item.get("path"))
        if not raw_path or Path(raw_path).is_absolute():
            continue
        observations.append({
            "kind": "ci_signal",
            "path": raw_path,
            "max_severity": _text(item.get("max_severity")) or "warning",
            "signal_count": item.get("signal_count", 0),
        })
    for item in signals.get("signals", []) if isinstance(signals.get("signals"), list) else []:
        if not isinstance(item, dict):
            continue
        raw_path = _text(item.get("path"))
        if not raw_path or Path(raw_path).is_absolute():
            continue
        observations.append({
            "kind": "ci_signal",
            "path": raw_path,
            "tool": _text(item.get("tool")),
            "category": _text(item.get("category")),
            "severity": _text(item.get("severity")) or "warning",
            "status": _text(item.get("status")) or "unknown",
            "matches": [value for value in (_text(item.get("summary")), _text(item.get("evidence")), _text(item.get("agent_hint"))) if value],
        })
    return observations



def _safe_artifact_json(artifacts: ArtifactStore, name: str) -> dict[str, object]:
    if not artifacts.exists(name):
        return {}
    try:
        value = artifacts.read_json(name)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _repo_relative_ci_path(repository: Path, value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path_text = value.strip().replace("\\", "/")
    path = Path(path_text)
    if not path.is_absolute():
        if ".." in Path(path_text).parts:
            return None
        return path_text
    try:
        return path.resolve().relative_to(repository.resolve()).as_posix()
    except (OSError, ValueError):
        pass
    parts = [part for part in path_text.split("/") if part]
    repo_name = repository.name
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] != repo_name:
            continue
        candidate = "/".join(parts[index + 1:])
        if candidate and ".." not in Path(candidate).parts:
            return candidate
    return None


def _normalize_ci_evidence_text(repository: Path, value: object) -> object:
    if not isinstance(value, str):
        return value
    raw_path = value.split(":", 1)[0]
    normalized = _repo_relative_ci_path(repository, raw_path)
    if normalized is None:
        return value
    suffix = ""
    if ":" in value:
        suffix = ":" + value.split(":", 1)[1]
    return normalized + suffix


def normalize_ci_signal_paths(repository: Path, payload: dict[str, object]) -> dict[str, object]:
    """Return CI signals with repository-relative paths where possible."""
    if not isinstance(payload, dict):
        return payload
    normalized_payload = deepcopy(payload)
    for section in ("path_index", "signals"):
        items = normalized_payload.get(section)
        if not isinstance(items, list):
            continue
        kept: list[object] = []
        for item in items:
            if not isinstance(item, dict):
                kept.append(item)
                continue
            raw_path = _text(item.get("path"))
            normalized_path = _repo_relative_ci_path(repository, raw_path)
            if raw_path and normalized_path is None:
                continue
            if raw_path and normalized_path != raw_path:
                item["raw_path"] = raw_path
                item["path"] = normalized_path
            if "evidence" in item:
                item["evidence"] = _normalize_ci_evidence_text(repository, item.get("evidence"))
            if "agent_hint" in item and isinstance(item.get("agent_hint"), str) and raw_path and normalized_path:
                item["agent_hint"] = str(item["agent_hint"]).replace(raw_path, normalized_path)
            kept.append(item)
        normalized_payload[section] = kept
    return normalized_payload


def repository_runtime_context(artifacts: ArtifactStore) -> dict[str, object]:
    """Return a compact git/CI context suitable for worker prompts."""
    git = _safe_artifact_json(artifacts, "git-run.json")
    ci = _safe_artifact_json(artifacts, "ci-status.json")
    signals = _safe_artifact_json(artifacts, "ci-signals.json")
    compact_signals = {
        "status": signals.get("status"),
        "summary": signals.get("summary", {}),
        "providers": signals.get("providers", {}),
        "warnings": signals.get("warnings", [])[:10] if isinstance(signals.get("warnings"), list) else [],
        "path_index": signals.get("path_index", [])[:25] if isinstance(signals.get("path_index"), list) else [],
        "signals": signals.get("signals", [])[:20] if isinstance(signals.get("signals"), list) else [],
    }
    return {
        "git": {
            "is_git_repository": git.get("is_git_repository"),
            "current_branch": git.get("current_branch"),
            "head": git.get("head"),
            "origin_main": git.get("origin_main"),
            "origin_url": git.get("origin_url"),
            "dirty": git.get("dirty"),
            "branch_mode": git.get("branch_mode"),
            "created_branch": git.get("created_branch"),
            "warnings": git.get("warnings", [])[:10] if isinstance(git.get("warnings"), list) else [],
        },
        "ci_status": {
            "providers": ci.get("providers", []),
            "warnings": ci.get("warnings", [])[:10] if isinstance(ci.get("warnings"), list) else [],
        },
        "ci_signals": compact_signals,
    }

def render_install_result(result: InstallResult) -> str:
    lines = ["## CI Installation"]
    if result.installed:
        lines.append("Installed:")
        lines.extend(f"- {path}" for path in result.installed)
    if result.skipped:
        lines.append("Skipped:")
        lines.extend(f"- {path}" for path in result.skipped)
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    if not result.installed and not result.skipped and not result.warnings:
        lines.append("No changes.")
    return "\n".join(lines) + "\n"
