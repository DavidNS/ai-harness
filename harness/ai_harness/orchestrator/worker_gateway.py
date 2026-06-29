"""WorkerGateway — invoke LLM workers via the configured provider.

Single responsibility: build the prompt, call provider.run_prompt(), write
job artifacts, and parse/validate the worker's response. Previously the
_invoke method and its private helpers on WorkerExchange.

Provider inspection helpers are module-level so worker_exchange.py can
import them without creating a circular dependency.
"""
from __future__ import annotations

import inspect
import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Mapping

from ..capabilities import CapabilityPolicy
from ..config import resource_path
from ..control_outputs import ControlFlowSignal, parse_control_output
from ..errors import HarnessError, ProviderPhaseError, ValidationError
from ..phases import PhaseValidationError, get_phase
from ..pipeline.state_machine import graph_for
from ..providers.base import Provider
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore
from .phase_repair import phase_contract_summary

# ------------------------------------------------------------------ #
# Provider inspection helpers (used here and re-imported by          #
# worker_exchange.py for backward compatibility with existing callers)#
# ------------------------------------------------------------------ #

def _accepts_provider_keyword(provider: Provider, name: str) -> bool:
    try:
        parameters = inspect.signature(provider.run_prompt).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(
        parameter.name == name or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _accepts_provider_progress(provider: Provider) -> bool:
    return _accepts_provider_keyword(provider, "progress")


def _accepts_provider_temp_dir(provider: Provider) -> bool:
    return _accepts_provider_keyword(provider, "temp_dir")


# ------------------------------------------------------------------ #
# Gateway                                                              #
# ------------------------------------------------------------------ #

class WorkerGateway:
    """Owns the provider call contract for one harness run.

    Cheap to instantiate — all heavy work happens inside ``invoke()``.
    """

    def __init__(
        self,
        provider: Provider | None,
        target: Path,
        state: StateStore,
        artifacts: ArtifactStore,
        progress: Callable[[str], None],
    ) -> None:
        self._provider = provider
        self._target = target
        self._state = state
        self._artifacts = artifacts
        self._progress = progress

    # ------------------------------------------------------------------ #
    # Debug snapshot (optional; gated by env var)                         #
    # ------------------------------------------------------------------ #

    def _worker_debug_enabled(self) -> bool:
        return os.environ.get("AI_HARNESS_WORKER_DEBUG") == "1"

    @staticmethod
    def _bounded_text(value: str, limit: int = 20_000) -> str:
        if len(value) <= limit:
            return value
        return value[:limit] + f"\n...[{len(value) - limit} chars truncated]"

    def _git_debug_command(self, command: list[str]) -> dict[str, object]:
        try:
            completed = subprocess.run(
                command,
                cwd=self._target,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception as exc:
            return {
                "command": list(command),
                "error": " ".join(str(exc).split())[:500] or type(exc).__name__,
            }
        return {
            "command": list(command),
            "exit_code": completed.returncode,
            "stdout": self._bounded_text(completed.stdout),
            "stderr": self._bounded_text(completed.stderr),
        }

    def _record_worker_debug_snapshot(self, job_id: str, phase: str, stage: str) -> None:
        if not self._worker_debug_enabled():
            return
        try:
            artifact = f"jobs/{job_id}/debug-{stage}.json"
            payload = {
                "schema_version": 1,
                "job_id": job_id,
                "phase": phase,
                "stage": stage,
                "commands": [
                    self._git_debug_command(["git", "status", "--short", "--untracked-files=all"]),
                    self._git_debug_command(["git", "diff", "--stat", "--"]),
                    self._git_debug_command(["git", "diff", "--name-status", "--"]),
                ],
            }
            self._artifacts.write_json(artifact, payload)
            self._state.record_artifact(artifact, phase.upper())
        except Exception as exc:
            self._progress(
                f"Worker debug snapshot skipped for {phase} {stage}: {' '.join(str(exc).split())[:200]}"
            )

    # ------------------------------------------------------------------ #
    # Job ID allocation                                                   #
    # ------------------------------------------------------------------ #

    def next_job_id(self) -> str:
        used = {
            parts[1]
            for item in self._artifacts.list()
            for parts in [item.split("/")]
            if len(parts) >= 3 and parts[0] == "jobs" and parts[1].startswith("J")
        }
        index = 1
        while f"J{index:04d}" in used:
            index += 1
        return f"J{index:04d}"

    # ------------------------------------------------------------------ #
    # Core invocation                                                     #
    # ------------------------------------------------------------------ #

    def invoke(
        self,
        name: str,
        inputs: Mapping[str, object],
        *,
        repair: Mapping[str, object] | None = None,
        parse_control: bool = True,
    ) -> str:
        if self._provider is None:
            raise HarnessError(f"phase {name} requires a configured provider")
        definition = get_phase(name)
        bounded = definition.build_input(inputs)
        if repair is not None:
            bounded["repair"] = dict(repair)
        bounded["decision_history"] = self._state.decision_history()
        bounded["escalation_history"] = self._state.escalation_history()
        manifest = definition.load_manifest(resource_path())
        permissions = CapabilityPolicy(manifest, self._target).worker_permissions()
        playbook = resource_path("workers", definition.playbook).read_text(encoding="utf-8")
        prompt = resource_path("prompts", definition.prompt).read_text(encoding="utf-8")
        worker_prompt = (
            f"{playbook}\n\n{prompt}\n\nReturn only the required artifact. Controller inputs:\n"
            + json.dumps(bounded, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        )
        provider_permissions = dict(permissions)
        provider_permissions["timeout_seconds"] = None
        state = self._state.load()
        job_id = self.next_job_id()
        temp_dir = self._artifacts.phase_temp_dir(state.run_id, name, job_id)
        self._artifacts.write_json(f"jobs/{job_id}/request.json", {
            "schema_version": 1,
            "job_id": job_id,
            "phase": name,
            "run_id": state.run_id,
            "prompt_chars": len(worker_prompt),
            "input_keys": sorted(bounded),
            "permissions": provider_permissions,
            "temp_dir": str(temp_dir),
        })
        self._state.record_artifact(f"jobs/{job_id}/request.json", name.upper())
        self._progress(
            f"Invoking {name} worker: job={job_id} timeout=unbounded prompt_chars={len(worker_prompt)}"
        )

        def provider_progress(stream: str, chunk: str) -> None:
            normalized = chunk.replace("\r\n", "\n").replace("\r", "\n")
            for line in normalized.split("\n"):
                if line:
                    self._progress(f"[{name} {stream}] {line}")

        run_kwargs: dict[str, object] = {"cwd": self._target, "permissions": provider_permissions}
        if _accepts_provider_progress(self._provider):
            run_kwargs["progress"] = provider_progress
        if _accepts_provider_temp_dir(self._provider):
            run_kwargs["temp_dir"] = temp_dir
        self._record_worker_debug_snapshot(job_id, name, "before")
        try:
            candidate = self._provider.run_prompt(worker_prompt, **run_kwargs)  # type: ignore[arg-type]
        finally:
            self._record_worker_debug_snapshot(job_id, name, "after")
        status = "timed out" if candidate.timed_out else f"exited {candidate.exit_code}"
        self._progress(
            f"Worker {name} {status} in {candidate.duration_seconds:.1f}s "
            f"stdout_chars={len(candidate.stdout)} stderr_chars={len(candidate.stderr)}"
            + (" truncated=true" if candidate.truncated else "")
        )
        self._artifacts.write_json(f"jobs/{job_id}/result.json", {
            "schema_version": 1,
            "job_id": job_id,
            "phase": name,
            "exit_code": candidate.exit_code,
            "duration_seconds": candidate.duration_seconds,
            "timed_out": candidate.timed_out,
            "truncated": candidate.truncated,
            "stdout": candidate.stdout,
            "stderr": candidate.stderr,
        })
        self._state.record_artifact(f"jobs/{job_id}/result.json", name.upper())
        if not candidate.succeeded:
            reason = "timed out" if candidate.timed_out else f"exited with {candidate.exit_code}"
            raise ProviderPhaseError(
                name,
                reason,
                stdout=candidate.stdout,
                stderr=candidate.stderr,
                truncated=candidate.truncated,
            )
        if parse_control:
            state = self._state.load()
            graph = graph_for(state.strategy, state.complexity)
            expected_origin = name.upper()
            try:
                control = parse_control_output(
                    candidate.stdout,
                    expected_origin=expected_origin,
                    active_graph_phase=state.current_phase,
                    graph=graph,
                )
            except ValidationError as exc:
                try:
                    raw_control = json.loads(candidate.stdout)
                except (TypeError, json.JSONDecodeError):
                    raise
                if not isinstance(raw_control, dict) or "kind" not in raw_control:
                    raise
                active_index = graph.index(state.current_phase) if state.current_phase in graph else 0
                repairable = PhaseValidationError(str(exc))
                setattr(repairable, "candidate_stdout", candidate.stdout)
                setattr(repairable, "candidate_job_id", job_id)
                setattr(repairable, "phase_name", name)
                setattr(repairable, "phase_artifact", definition.artifact)
                setattr(repairable, "phase_contract", phase_contract_summary(definition))
                setattr(repairable, "control_output_contract", {
                    "kind": raw_control.get("kind"),
                    "expected_origin": expected_origin,
                    "active_graph_phase": state.current_phase,
                    "graph": list(graph),
                    "allowed_escalation_targets": list(graph[:active_index]),
                })
                raise repairable from exc
            if control is not None:
                raise ControlFlowSignal(control)
        try:
            definition.validate(candidate.stdout)
        except PhaseValidationError as exc:
            setattr(exc, "candidate_stdout", candidate.stdout)
            setattr(exc, "candidate_job_id", job_id)
            setattr(exc, "phase_name", name)
            setattr(exc, "phase_artifact", definition.artifact)
            setattr(exc, "phase_contract", phase_contract_summary(definition))
            raise
        return candidate.stdout
