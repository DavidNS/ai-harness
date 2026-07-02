"""Local CI adapter for template status, installation, and fixture signals."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from harness_v2.backend.ports.ci import CIPort, CiInstallRequest, CiInstallResult, CiSignalRequest

_TEMPLATE_VERSION = "1"
_MARKER = "ai-harness-ci-template:"
_ROOT = Path(__file__).resolve().parents[3]
_GITHUB_TEMPLATE = _ROOT / "harness" / "ci_templates" / "github" / "ai-harness-ci.yml"
_GITHUB_DESTINATION = Path(".github/workflows/ai-harness-ci.yml")
_GITLAB_DESTINATION = Path(".gitlab-ci.yml")


class LocalCIAdapter(CIPort):
    def install_templates(self, request: CiInstallRequest) -> CiInstallResult:
        repository = request.repository.resolve()
        providers = ("github", "gitlab") if request.target == "both" else (request.target,)
        installed: list[str] = []
        skipped: list[str] = []
        warnings: list[str] = []
        for provider in providers:
            path, skip, warning = self._install_one(repository, provider, force=request.force)
            if path:
                installed.append(path)
            if skip:
                skipped.append(skip)
            if warning:
                warnings.append(warning)
        return CiInstallResult(tuple(installed), tuple(skipped), tuple(warnings))

    def status(self, repository: Path) -> dict[str, object]:
        repository = Path(repository).resolve()
        providers: list[dict[str, object]] = []
        warnings: list[str] = []
        for path in _ci_files(repository):
            relative = path.relative_to(repository).as_posix()
            provider = "gitlab" if relative == ".gitlab-ci.yml" else "github"
            content = path.read_text(encoding="utf-8", errors="ignore")
            managed = _managed_digest(content)
            expected = _expected_digest(provider)
            entry: dict[str, object] = {
                "provider": provider,
                "path": relative,
                "managed": managed is not None,
                "in_sync": expected is not None and managed == expected,
            }
            providers.append(entry)
            if managed is None:
                warnings.append(f"CI file {relative} exists but is not managed by ai-harness; no sync status is available.")
            elif expected is None:
                warnings.append(f"CI file {relative} is managed by ai-harness but no bundled template is available.")
            elif managed != expected:
                warnings.append(f"CI file {relative} is managed by ai-harness but does not match the bundled template.")
        if not providers:
            warnings.append("No CI pipeline is installed. CI signals are unavailable until a supported pipeline is configured.")
        return {
            "schema_version": 1,
            "template_version": _TEMPLATE_VERSION,
            "providers": providers,
            "warnings": warnings,
        }

    def collect_signals(self, request: CiSignalRequest) -> dict[str, object]:
        if request.ci_mode == "off":
            return _ci_unavailable("github", "GitHub baseline CI collection is disabled", scope=request.scope, ref=request.ref)
        repository = request.repository.resolve()
        fixture = repository / "signals" / "ai-harness-signals.json"
        if not fixture.is_file():
            return _ci_unavailable("local", "No local ai-harness CI signals artifact was found", scope=request.scope, ref=request.ref)
        try:
            payload = json.loads(fixture.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return _ci_unavailable("local", "Local ai-harness CI signals artifact was malformed", status="problem_gathering_info", scope=request.scope, ref=request.ref)
        if not isinstance(payload, dict):
            return _ci_unavailable("local", "Local ai-harness CI signals artifact was malformed", status="problem_gathering_info", scope=request.scope, ref=request.ref)
        return _normalize_local_signals(payload, request)

    def _install_one(self, repository: Path, provider: str, *, force: bool) -> tuple[str | None, str | None, str | None]:
        if provider == "github":
            source = _GITHUB_TEMPLATE
            destination = repository / _GITHUB_DESTINATION
        elif provider == "gitlab":
            source = None
            destination = repository / _GITLAB_DESTINATION
        else:
            raise ValueError(f"unsupported CI provider: {provider}")
        relative = destination.relative_to(repository).as_posix()
        if source is None or not source.is_file():
            return None, relative, f"{relative} could not be installed because no bundled {provider} template is available."
        content = _template_text(source, provider)
        if destination.exists():
            existing = destination.read_text(encoding="utf-8", errors="ignore")
            if _managed_digest(existing) is None and not force:
                return None, relative, f"{relative} already exists and is not managed by ai-harness; use force to replace it."
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return relative, None, None


def _template_text(source: Path, provider: str) -> str:
    raw = source.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"# {_MARKER} provider={provider} version={_TEMPLATE_VERSION} sha256={digest}\n{raw}"


def _managed_digest(content: str) -> str | None:
    first = content.splitlines()[0] if content else ""
    match = re.search(rf"{re.escape(_MARKER)} .*sha256=([a-f0-9]{{64}})", first)
    return match.group(1) if match else None


def _expected_digest(provider: str) -> str | None:
    if provider != "github" or not _GITHUB_TEMPLATE.is_file():
        return None
    return hashlib.sha256(_GITHUB_TEMPLATE.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _ci_files(repository: Path) -> list[Path]:
    files: list[Path] = []
    github = repository / ".github" / "workflows"
    if github.is_dir():
        files.extend(sorted(path for path in github.iterdir() if path.suffix in {".yml", ".yaml"} and path.is_file()))
    gitlab = repository / ".gitlab-ci.yml"
    if gitlab.is_file():
        files.append(gitlab)
    return files


def _ci_unavailable(provider: str, reason: str, *, status: str = "unavailable", scope: str = "unknown", ref: str | None = None) -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "ai_harness_ci_signals",
        "provider": provider,
        "scope": scope,
        "ref": ref,
        "status": status,
        "reason": reason,
        "providers": {provider: {"status": status, "signal_count": 0}},
        "summary": {"status": status, "signal_count": 0, "provider_count": 1},
        "warnings": [],
        "path_index": [],
        "signals": [],
    }


def _normalize_local_signals(payload: dict[str, object], request: CiSignalRequest) -> dict[str, object]:
    signals = payload.get("signals") if isinstance(payload.get("signals"), list) else []
    path_index = payload.get("path_index") if isinstance(payload.get("path_index"), list) else []
    warnings = [item for item in payload.get("warnings", []) if isinstance(item, str)] if isinstance(payload.get("warnings"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    status = str(payload.get("status") or summary.get("status") or "ready")
    provider = str(payload.get("provider") or "local")
    return {
        "schema_version": 2,
        "kind": "ai_harness_ci_signals",
        "provider": provider,
        "scope": str(payload.get("scope") or request.scope),
        "ref": ref,
        "status": status,
        "providers": {provider: {"status": status, "signal_count": len(signals)}},
        "summary": {"status": status, "signal_count": len(signals), "provider_count": 1},
        "warnings": warnings,
        "path_index": path_index,
        "signals": signals,
    }
