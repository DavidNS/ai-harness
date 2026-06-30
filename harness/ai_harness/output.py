"""Stable user-facing rendering for harness runs."""

from __future__ import annotations

import shlex
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .router import RouteDecision
from .strategy import StrategyDecision


@dataclass(frozen=True, slots=True)
class CommandContext:
    target_repository: Path
    runner: Path
    python: str = sys.executable


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    route: RouteDecision
    strategy: StrategyDecision
    phases: tuple[str, ...]
    task_summary: str
    artifacts: tuple[str, ...]
    outcome: str
    snapshot_path: Path | None
    warnings: tuple[str, ...] = ()
    control: Mapping[str, object] | None = None


def default_command_context(target_repository: Path, runner: Path | None = None) -> CommandContext:
    script = runner or Path(__file__).resolve().parents[1] / "run.py"
    return CommandContext(Path(target_repository).resolve(), Path(script).resolve())


def _base_command(command_context: CommandContext | None) -> str:
    if command_context is None:
        return "ai-harness"
    return shlex.join([
        command_context.python,
        "-B",
        str(command_context.runner),
        "--cwd",
        str(command_context.target_repository),
    ])


def render_resume_command(command_context: CommandContext | None, run_id: str, *, model: str | None = None) -> str:
    command = f"{_base_command(command_context)} --resume {shlex.quote(run_id)}"
    if model:
        command += f" --model {shlex.quote(model)}"
    return command


def render_archive_command(command_context: CommandContext | None, run_id: str) -> str:
    return f"{_base_command(command_context)} --archive {shlex.quote(run_id)}"


def _score_section(request: Mapping[str, object]) -> str:
    scores = request.get("scores", {})
    if not isinstance(scores, Mapping) or not scores:
        return ""
    ranked = request.get("ranked_paths", [])
    if isinstance(ranked, list) and all(isinstance(item, str) for item in ranked):
        paths = [path for path in ranked if path in scores]
    else:
        paths = []
    paths.extend(path for path in scores if path not in paths)
    lines = []
    for path in paths:
        score = scores.get(path)
        if isinstance(score, int):
            lines.append(f"- {path}: {score}")
    return "Scores:\n" + "\n".join(lines) + "\n\n" if lines else ""


def _signal_section(request: Mapping[str, object]) -> str:
    score_signals = request.get("score_signals", {})
    if not isinstance(score_signals, Mapping) or not score_signals:
        return ""
    ranked = request.get("ranked_paths", [])
    if isinstance(ranked, list) and all(isinstance(item, str) for item in ranked):
        paths = [path for path in ranked if path in score_signals]
    else:
        paths = []
    paths.extend(path for path in score_signals if path not in paths)
    lines = []
    for path in paths:
        signals = score_signals.get(path)
        if isinstance(signals, list) and signals:
            lines.append(f"- {path}: " + ", ".join(str(item) for item in signals))
    return "Signals:\n" + "\n".join(lines) + "\n\n" if lines else ""


def render_pending_decision(
    run_id: str,
    decision_id: str,
    request: Mapping[str, object],
    command_context: CommandContext | None = None,
    *,
    model: str | None = None,
) -> str:
    context = request.get("context", [])
    if isinstance(context, list) and context:
        context_text = "\n".join(f"- {item}" for item in context)
    else:
        context_text = "- No additional context provided."
    options = request.get("options", [])
    option_text = ""
    if isinstance(options, list) and options:
        lines = []
        for option in options:
            if not isinstance(option, dict):
                continue
            lines.append(f"- {option.get('id')}: {option.get('label')} - {option.get('consequence')}")
        if lines:
            option_text = "\n\nOptions:\n" + "\n".join(lines)
    resume = render_resume_command(command_context, run_id, model=model)
    return (
        "## Decision Required\n"
        f"Run ID: {run_id}\n"
        f"Decision ID: {decision_id}\n"
        f"Origin: {request.get('origin_phase', 'unknown')}\n\n"
        "Question:\n"
        f"{request.get('question', '')}\n\n"
        f"{_score_section(request)}"
        f"{_signal_section(request)}"
        "Context:\n"
        f"{context_text}{option_text}\n\n"
        "Resume:\n"
        f"{resume} --answer <answer> --selected-option <option-id>\n"
        "Legacy file resume:\n"
        f"{resume} --answer-file <path>\n"
        "Archive:\n"
        f"{render_archive_command(command_context, run_id)}\n"
    )


def render_result(result: RunResult, command_context: CommandContext | None = None) -> str:
    if result.outcome == "waiting_for_user" and result.control is not None:
        decision_id = str(result.control.get("decision_id", ""))
        request = result.control.get("request", {})
        if isinstance(request, Mapping):
            model = None
            if result.control is not None:
                raw_model = result.control.get("selected_model")
                if isinstance(raw_model, str) and raw_model.strip():
                    model = raw_model.strip()
            return render_pending_decision(result.run_id, decision_id, request, command_context, model=model)
    artifacts = "\n".join(f"- {name}" for name in result.artifacts) or "- None"
    warnings = "\nWarnings: " + "; ".join(result.warnings) if result.warnings else ""
    snapshot = str(result.snapshot_path) if result.snapshot_path else "unavailable"
    control_artifact = ""
    if result.control is not None and result.control.get("artifact"):
        control_artifact = f"\nControl Artifact: {result.control['artifact']}"
    return (
        "## Router\n"
        f"Mode: {result.route.mode}\nIntent: {result.route.intent}\n"
        f"Confidence: {result.route.confidence:.2f}\nSource: {result.route.source}\n\n"
        "## Flow\n"
        f"Selected: {result.strategy.strategy}\n"
        f"Reason: {result.strategy.reason}\n\n"
        "## Bundles\n"
        f"Phases: {' -> '.join(result.phases)}\nTasks: {result.task_summary}\n\n"
        f"## Artifacts\n{artifacts}\n\n"
        "## Result\n"
        f"Status: {result.outcome}\nRun ID: {result.run_id}\nSnapshot: {snapshot}{control_artifact}{warnings}\n"
    )
