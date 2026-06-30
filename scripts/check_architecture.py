#!/usr/bin/env python3
"""Repository-native architecture guardrails for ai-harness."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "harness"
sys.path.insert(0, str(HARNESS))

from ai_harness.contracts.enums import PhaseName  # noqa: E402
from ai_harness.models import Strategy  # noqa: E402
from ai_harness.phases import PHASE_DEFINITIONS  # noqa: E402
from ai_harness.pipeline.state_machine import GRAPHS  # noqa: E402

NOOP_PHASES = {"COMPLETED"}
EXTRA_DISPATCH_PHASES = set()
REGISTRY_ONLY_PHASES = {"explore", "purpose", "spec", "design", "tasks", "learning", "explorer", "explorer_intake", "explorer_discovery", "explorer_decision", "explorer_artifact", "explorer_review", "explorer_distill", "implement", "test", "review", "knowledge_synthesis", "knowledge_review", "explore_request_understanding", "explore_clarification_gate", "explore_triage", "explore_evidence_plan", "explore_evidence_collection", "explore_ci_barrier", "explore_evidence_normalization", "explore_outcome_synthesis", "explore_review"}
ORCHESTRATOR_IMPORT_ALLOWLIST = {Path("harness/run.py")}
RUN_CONTEXT_CONSUMERS = {
    Path("harness/ai_harness/orchestrator/context.py"),
    Path("harness/ai_harness/orchestrator/lifecycle.py"),
    Path("harness/ai_harness/orchestrator/phase_execution.py"),
    Path("harness/ai_harness/orchestrator/control_output_handler.py"),
    Path("harness/ai_harness/orchestrator/result_publication.py"),
    Path("harness/ai_harness/orchestrator/task_execution.py"),
    Path("harness/ai_harness/orchestrator/task_plan_execution.py"),
    Path("harness/ai_harness/orchestrator/analysis_quality.py"),
    Path("harness/ai_harness/orchestrator/explorer_artifacts.py"),
    Path("harness/ai_harness/orchestrator/explore_pipeline.py"),
    Path("harness/ai_harness/orchestrator/explorer_flow.py"),
    Path("harness/ai_harness/orchestrator/explorer_inputs.py"),
    Path("harness/ai_harness/orchestrator/worker_exchange.py"),
}
STATE_MUTATION_ALLOWLIST = {
    Path("harness/ai_harness/stores/state/store.py"),
    Path("harness/ai_harness/pipeline/tdd_loop/loop.py"),
}
STATE_SAVE_ALLOWLIST = {
    Path("harness/ai_harness/stores/state/store.py"),
    Path("harness/ai_harness/orchestrator/run_initializer.py"),
    Path("harness/ai_harness/pipeline/tdd_loop/loop.py"),
}
STATE_UPDATE_ALLOWLIST = {
    Path("harness/ai_harness/stores/state/store.py"),
    Path("harness/ai_harness/orchestrator/routing_coordinator.py"),
    Path("harness/ai_harness/orchestrator/strategy_persister.py"),
    Path("harness/ai_harness/orchestrator/task_plan_execution.py"),
    Path("harness/ai_harness/orchestrator/control_output_handler.py"),
}
SOURCE_LINE_BUDGET = 400
SOURCE_LINE_EXCEPTIONS = {Path("harness/ai_harness/orchestrator/publishing.py"): 525}
INTEGRATION_LINE_BUDGET = 350
INTEGRATION_LINE_EXCEPTIONS = {
    Path("tests/integration/test_decision_gates.py"): 525,
    Path("tests/integration/test_full_sdd.py"): 425,
}


@dataclass
class Finding:
    level: str
    code: str
    category: str
    message: str
    path: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "level": self.level,
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "path": self.path,
        }
        if self.details:
            data["details"] = self.details
        return data


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        return [finding.message for finding in self.findings if finding.level == "error"]

    @property
    def warnings(self) -> list[str]:
        return [finding.message for finding in self.findings if finding.level == "warning"]

    def error(
        self,
        message: str,
        *,
        code: str = "architecture.error",
        category: str = "contract",
        path: str | Path | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._add("error", message, code=code, category=category, path=path, details=details)

    def warn(
        self,
        message: str,
        *,
        code: str = "architecture.warning",
        category: str = "maintainability",
        path: str | Path | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._add("warning", message, code=code, category=category, path=path, details=details)

    def _add(
        self,
        level: str,
        message: str,
        *,
        code: str,
        category: str,
        path: str | Path | None,
        details: dict[str, object] | None,
    ) -> None:
        self.findings.append(
            Finding(
                level=level,
                code=code,
                category=category,
                message=message,
                path=str(path) if path is not None else None,
                details=details or {},
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "failed" if self.errors else "passed",
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def rel(path: Path) -> Path:
    return path.relative_to(ROOT)


def python_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        if root.exists():
            files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def phase_value(value: object) -> str:
    return value.value if isinstance(value, PhaseName) else str(value)


def dispatcher_phases() -> set[str]:
    tree = parse(ROOT / "harness/ai_harness/orchestrator/phase_execution.py")
    phases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if (
                    isinstance(key, ast.Attribute)
                    and isinstance(key.value, ast.Name)
                    and key.value.id == "PhaseName"
                ):
                    phases.add(PhaseName[key.attr].value)
    return phases


def check_graph_contract(report: Report) -> None:
    if set(GRAPHS) != set(Strategy):
        report.error("pipeline graphs must cover every Strategy exactly")
    known = {phase.value for phase in PhaseName}
    for strategy, graph in GRAPHS.items():
        values = [phase_value(phase) for phase in graph]
        if any(value not in known for value in values):
            pass
        if len(values) != len(set(values)):
            report.error(f"{strategy.value} graph contains duplicate phases")
        unknown = sorted(set(values) - known)
        if unknown:
            report.error(f"{strategy.value} graph contains phases outside PhaseName: {unknown}")
        non_bundle = sorted(set(values) - {
            "EXPLORE_BUNDLE", "PROPOSAL_BUNDLE", "SPEC_BUNDLE",
            "DESIGN_BUNDLE", "TASKS_BUNDLE", "TDD_BUNDLE",
        })
        if non_bundle:
            report.error(f"{strategy.value} graph contains non-bundle phases: {non_bundle}")


def check_dispatcher_contract(report: Report) -> None:
    graph_phases = {phase_value(phase) for graph in GRAPHS.values() for phase in graph}
    dispatched = dispatcher_phases()
    missing = sorted(graph_phases - dispatched)
    if missing:
        report.error(f"graph phases missing dispatcher/no-op handlers: {missing}")
    extra = sorted(dispatched - graph_phases - EXTRA_DISPATCH_PHASES)
    if extra:
        report.error(f"dispatcher handles phases not in graphs or allowlist: {extra}")


def check_phase_resources(report: Report) -> None:
    harness_root = ROOT / "harness"
    for name, phase in PHASE_DEFINITIONS.items():
        for folder, filename in (("workers", phase.playbook), ("prompts", phase.prompt), ("capabilities", phase.capability_manifest)):
            if not (harness_root / folder / filename).is_file():
                report.error(f"phase {name} missing {folder}/{filename}")
        manifest_path = harness_root / "capabilities" / phase.capability_manifest
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                report.error(f"phase {name} capability manifest is invalid JSON: {exc}")
                continue
            if manifest.get("phase") != phase.name:
                report.error(f"phase {name} capability manifest phase mismatch")
    graph_worker_phases = {phase_value(phase).lower() for graph in GRAPHS.values() for phase in graph}
    graph_worker_phases -= {phase.lower() for phase in NOOP_PHASES}
    registry_missing = sorted(graph_worker_phases - set(PHASE_DEFINITIONS) - {"explore_bundle", "proposal_bundle", "spec_bundle", "design_bundle", "tasks_bundle", "tdd_bundle"})
    if registry_missing:
        report.error(f"graph worker phases missing registry definitions: {registry_missing}")
    registry_extra = sorted(set(PHASE_DEFINITIONS) - graph_worker_phases - REGISTRY_ONLY_PHASES)
    if registry_extra:
        report.error(f"registry phases are not used by graphs or allowlist: {registry_extra}")


def imported_modules(tree: ast.Module) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def check_import_boundaries(report: Report) -> None:
    for path in python_files(ROOT / "harness", ROOT / "scripts"):
        relative = rel(path)
        if relative in ORCHESTRATOR_IMPORT_ALLOWLIST:
            continue
        modules = imported_modules(parse(path))
        if "ai_harness.orchestrator" in modules:
            report.error(f"{relative} must not import ai_harness.orchestrator")


def attr_chain(node: ast.AST) -> list[str]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return list(reversed(parts))


def assigned_state_attrs(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    tracked = {"current_phase", "completed_phases", "failed_phases", "tasks", "status", "pending_decision"}
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            for child in ast.walk(target):
                if not isinstance(child, ast.Attribute) or child.attr not in tracked:
                    continue
                chain = attr_chain(child)
                if chain[0] in {"state", "terminal"} or chain[-2:] in (["self", "_state"], ["self", "state"]):
                    names.add(child.attr)
    return names


def calls_state_store_method(tree: ast.Module, method: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != method:
            continue
        chain = attr_chain(node.func.value)
        if chain in (["self", "_state"], ["self", "state"], ["self", "_ctx", "state"]):
            return True
    return False


def check_state_mutation(report: Report) -> None:
    for path in python_files(ROOT / "harness/ai_harness"):
        relative = rel(path)
        tree = parse(path)
        mutations = assigned_state_attrs(tree)
        if mutations and relative not in STATE_MUTATION_ALLOWLIST:
            report.error(f"{relative} mutates RunState-like fields directly: {sorted(mutations)}")
        if calls_state_store_method(tree, "save") and relative not in STATE_SAVE_ALLOWLIST:
            report.error(f"{relative} calls StateStore.save outside allowlist")
        if calls_state_store_method(tree, "update") and relative not in STATE_UPDATE_ALLOWLIST:
            report.error(f"{relative} calls StateStore.update outside allowlist")


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def check_budgets(report: Report) -> None:
    for path in python_files(ROOT / "harness/ai_harness", ROOT / "harness/cli", ROOT / "harness/run.py"):
        relative = rel(path)
        budget = SOURCE_LINE_EXCEPTIONS.get(relative, SOURCE_LINE_BUDGET)
        count = line_count(path)
        if count > budget:
            report.warn(
                f"{relative} has {count} lines; budget is {budget}",
                code="line_budget.source",
                category="budget",
                path=relative,
                details={"lines": count, "budget": budget, "over_by": count - budget},
            )
    for path in python_files(ROOT / "tests/integration"):
        relative = rel(path)
        budget = INTEGRATION_LINE_EXCEPTIONS.get(relative, INTEGRATION_LINE_BUDGET)
        count = line_count(path)
        if count > budget:
            report.warn(
                f"{relative} has {count} lines; budget is {budget}",
                code="line_budget.integration",
                category="budget",
                path=relative,
                details={"lines": count, "budget": budget, "over_by": count - budget},
            )
    for path in python_files(ROOT / "harness/ai_harness"):
        relative = rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = parse(path)
        imports_run_context = any(
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.endswith("context")
            and any(alias.name == "RunContext" for alias in node.names)
            for node in ast.walk(tree)
        )
        if imports_run_context and relative not in RUN_CONTEXT_CONSUMERS:
            report.warn(
                f"{relative} consumes RunContext outside current boundary list",
                code="coupling.run_context",
                category="coupling",
                path=relative,
            )
        if "orch: object" in text or any(
            isinstance(node, ast.Name) and node.id == "_orch" for node in ast.walk(tree)
        ):
            report.warn(
                f"{relative} contains broad orchestrator coupling markers",
                code="coupling.orchestrator_marker",
                category="coupling",
                path=relative,
            )


def run_checks() -> Report:
    report = Report()
    check_graph_contract(report)
    check_dispatcher_contract(report)
    check_phase_resources(report)
    check_import_boundaries(report)
    check_state_mutation(report)
    check_budgets(report)
    return report


def summary_line(report: Report) -> str:
    if report.errors:
        return f"Architecture check failed: {len(report.errors)} error(s), {len(report.warnings)} warning(s)"
    return f"Architecture check passed: {len(report.warnings)} warning(s)"


def render_text(report: Report) -> str:
    lines: list[str] = []
    lines.extend(f"WARN: {warning}" for warning in report.warnings)
    lines.extend(f"ERROR: {error}" for error in report.errors)
    lines.append(summary_line(report))
    return "\n".join(lines)


def render_summary(report: Report) -> str:
    return summary_line(report)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="emit structured JSON findings")
    output.add_argument("--summary", action="store_true", help="emit only the final summary line")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_checks()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    elif args.summary:
        print(render_summary(report))
    else:
        print(render_text(report))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
