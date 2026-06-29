#!/usr/bin/env python3
"""Generate an agent-ready CI signal report for EXPLORE."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SIGNALS = ROOT / "signals"
RAW = SIGNALS / "raw"


def _run(argv: list[str], *, raw_name: str) -> dict[str, object]:
    RAW.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        returncode = completed.returncode
    except FileNotFoundError as exc:
        stdout = ""
        stderr = str(exc)
        returncode = 127
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else "command timed out"
        returncode = 124
    (RAW / f"{raw_name}.stdout").write_text(stdout, encoding="utf-8")
    (RAW / f"{raw_name}.stderr").write_text(stderr, encoding="utf-8")
    return {"argv": argv, "returncode": returncode, "stdout": stdout, "stderr": stderr}


def _json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _git(args: list[str]) -> str:
    result = _run(["git", *args], raw_name="git-" + "-".join(args[:2]))
    if result["returncode"] != 0:
        return ""
    return str(result["stdout"]).strip()


def _agent_hint(path: str | None) -> str:
    if path:
        return f"Inspect {path} if this path is relevant to the request."
    return "Use this as repository-level context."


def _signal(
    signals: list[dict[str, object]],
    *,
    tool: str,
    category: str,
    severity: str,
    path: str | None,
    summary: str,
    evidence: str,
    confidence: str = "medium",
    agent_hint: str | None = None,
) -> None:
    signals.append({
        "id": f"S{len(signals) + 1}",
        "tool": tool,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "path": path or "",
        "summary": " ".join(summary.split())[:300],
        "evidence": " ".join(evidence.split())[:500],
        "agent_hint": agent_hint or _agent_hint(path),
    })


def _collect_ruff(signals: list[dict[str, object]]) -> int:
    raw_path = RAW / "ruff.json"
    result = _run(["ruff", "check", "harness/", "--output-format", "json"], raw_name="ruff")
    raw_path.write_text(str(result["stdout"]), encoding="utf-8")
    data = _json_file(raw_path)
    if isinstance(data, list):
        for item in data[:50]:
            if not isinstance(item, dict):
                continue
            location = item.get("location") if isinstance(item.get("location"), dict) else {}
            path = str(item.get("filename", ""))
            row = location.get("row", "")
            code = str(item.get("code", "ruff"))
            message = str(item.get("message", "Ruff finding"))
            _signal(
                signals,
                tool="ruff",
                category="lint",
                severity="warning",
                path=path,
                summary=f"{code}: {message}",
                evidence=f"{path}:{row}",
                confidence="high",
            )
    return int(result["returncode"])


def _collect_mypy(signals: list[dict[str, object]]) -> int:
    result = _run(["python", "-m", "mypy"], raw_name="mypy")
    for line in str(result["stdout"]).splitlines()[:50]:
        if ": error:" not in line:
            continue
        path = line.split(":", 1)[0]
        _signal(
            signals,
            tool="mypy",
            category="typing",
            severity="warning",
            path=path,
            summary=line,
            evidence=line,
            confidence="medium",
        )
    return int(result["returncode"])


def _collect_architecture(signals: list[dict[str, object]]) -> int:
    raw_path = RAW / "architecture.json"
    result = _run(["python3", "-B", "scripts/check_architecture.py", "--json"], raw_name="architecture")
    raw_path.write_text(str(result["stdout"]), encoding="utf-8")
    data = _json_file(raw_path)
    if isinstance(data, dict):
        findings = data.get("findings", [])
        if isinstance(findings, list):
            for item in findings[:80]:
                if not isinstance(item, dict):
                    continue
                _signal(
                    signals,
                    tool="check_architecture",
                    category=str(item.get("category", "architecture")),
                    severity="error" if item.get("level") == "error" else "warning",
                    path=str(item.get("path") or ""),
                    summary=str(item.get("message", "Architecture finding")),
                    evidence=json.dumps(item.get("details", {}), sort_keys=True),
                    confidence="high",
                    agent_hint="Treat architecture errors as strong evidence for constraints.",
                )
    return int(result["returncode"])


def _collect_pytest(signals: list[dict[str, object]], *, scope: str) -> int:
    result = _run(
        ["python", "-m", "pytest", "-q", "--tb=short", "--junitxml", "signals/raw/pytest-junit.xml"],
        raw_name="pytest",
    )
    if result["returncode"] != 0:
        lines = [line for line in str(result["stdout"]).splitlines() if line.strip()]
        excerpt = "\n".join(lines[-20:])
        summary = "Pytest failed on trunk baseline." if scope == "trunk_baseline" else "Pytest failed for this CI run."
        _signal(
            signals,
            tool="pytest",
            category="tests",
            severity="error",
            path="",
            summary=summary,
            evidence=excerpt or str(result["stderr"]),
            confidence="high",
            agent_hint="Use baseline failures as constraints; treat branch-only failures as implementation risk.",
        )
    return int(result["returncode"])


def _collect_semgrep(signals: list[dict[str, object]]) -> int:
    raw_path = RAW / "semgrep.json"
    result = _run(["semgrep", "scan", "--config", "auto", "--json", "--output", str(raw_path)], raw_name="semgrep")
    data = _json_file(raw_path)
    if isinstance(data, dict):
        findings = data.get("results", [])
        if isinstance(findings, list):
            for item in findings[:80]:
                if not isinstance(item, dict):
                    continue
                extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
                metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
                start = item.get("start") if isinstance(item.get("start"), dict) else {}
                path = str(item.get("path", ""))
                _signal(
                    signals,
                    tool="semgrep",
                    category=str(metadata.get("category", "static-analysis")),
                    severity=str(extra.get("severity", "warning")).casefold(),
                    path=path,
                    summary=str(extra.get("message", "Semgrep finding")),
                    evidence=f"{path}:{start.get('line', '')}",
                    confidence="medium",
                    agent_hint="Confirm whether this Semgrep finding is relevant before using it in PURPOSE.",
                )
    code = int(result["returncode"])
    return 0 if code == 1 else code


def _github_run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not repository or not run_id:
        return ""
    return f"{server.rstrip('/')}/{repository}/actions/runs/{run_id}"


def _scope(branch: str, base_ref: str) -> str:
    if branch == "main" and not base_ref:
        return "trunk_baseline"
    if base_ref:
        return "pull_request"
    return "run_branch"


def _path_index(signals: list[dict[str, object]]) -> list[dict[str, object]]:
    order = {"error": 4, "critical": 4, "high": 3, "warning": 2, "medium": 2, "low": 1, "info": 0}
    entries: dict[str, dict[str, object]] = {}
    for signal in signals:
        path = str(signal.get("path", ""))
        if not path:
            continue
        entry = entries.setdefault(path, {"path": path, "signal_count": 0, "max_severity": ""})
        entry["signal_count"] = int(entry["signal_count"]) + 1
        severity = str(signal.get("severity", ""))
        if order.get(severity, 0) > order.get(str(entry.get("max_severity", "")), 0):
            entry["max_severity"] = severity
    return [entries[path] for path in sorted(entries)]


def main() -> int:
    SIGNALS.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    head_ref = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or _git(["branch", "--show-current"])
    base_ref = os.environ.get("GITHUB_BASE_REF", "")
    scope = _scope(head_ref, base_ref)
    signals: list[dict[str, object]] = []
    statuses = {
        "ruff": _collect_ruff(signals),
        "mypy": _collect_mypy(signals),
        "architecture": _collect_architecture(signals),
        "pytest": _collect_pytest(signals, scope=scope),
        "semgrep": _collect_semgrep(signals),
    }
    report = {
        "schema_version": 2,
        "kind": "ai_harness_ci_signals",
        "provider": "github" if os.environ.get("GITHUB_ACTIONS") else "local",
        "scope": scope,
        "base_ref": base_ref,
        "base_sha": "",
        "head_ref": head_ref,
        "head_sha": os.environ.get("GITHUB_SHA") or _git(["rev-parse", "HEAD"]),
        "commit": os.environ.get("GITHUB_SHA") or _git(["rev-parse", "HEAD"]),
        "branch": head_ref,
        "run": {
            "run_id": os.environ.get("GITHUB_RUN_ID", ""),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            "workflow_name": os.environ.get("GITHUB_WORKFLOW", ""),
            "url": _github_run_url(),
            "event": os.environ.get("GITHUB_EVENT_NAME", ""),
            "created_at": "",
        },
        "pipeline": {
            "id": os.environ.get("CI_PIPELINE_ID", "") or os.environ.get("GITHUB_RUN_ID", ""),
            "url": os.environ.get("CI_PIPELINE_URL", "") or _github_run_url(),
            "source": os.environ.get("CI_PIPELINE_SOURCE", "") or os.environ.get("GITHUB_EVENT_NAME", ""),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "status": "failed" if any(statuses.values()) else "passed",
            "signal_count": len(signals),
            "tool_status": statuses,
        },
        "path_index": _path_index(signals),
        "signals": signals[:200],
        "raw_artifacts": [
            "signals/raw/ruff.json",
            "signals/raw/mypy.stdout",
            "signals/raw/architecture.json",
            "signals/raw/pytest-junit.xml",
            "signals/raw/semgrep.json",
        ],
    }
    (SIGNALS / "ai-harness-signals.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 1 if any(statuses.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
