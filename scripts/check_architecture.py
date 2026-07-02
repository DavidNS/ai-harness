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
REGISTRY_ONLY_PHASES = {"explore", "purpose", "spec", "design", "tasks", "learning", "explorer", "explorer_intake", "explorer_discovery", "explorer_decision", "explorer_artifact", "explorer_review", "explorer_distill", "implement", "test", "review", "knowledge_synthesis", "knowledge_review", "explore_request_profile", "explore_evidence_digest", "explore_delta", "explore_request_understanding", "explore_clarification_gate", "explore_triage", "explore_evidence_plan", "explore_evidence_collection", "explore_ci_barrier", "explore_evidence_normalization", "explore_outcome_synthesis", "explore_review"}
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
SOURCE_LINE_EXCEPTIONS = {
    Path("harness/ai_harness/orchestrator/publishing.py"): 525,
    # EXPLORE is intentionally covered by budgets while remaining temporarily
    # above the default until bundle helpers are split.
    Path("harness_v2/backend/application/phase_artifacts/explore.py"): 1200,
    # File-backed state and artifacts share security helpers until storage
    # adapters are split by backend port.
    Path("harness_v2/adapters/storage/file.py"): 525,
}
INTEGRATION_LINE_BUDGET = 350
INTEGRATION_LINE_EXCEPTIONS = {
    Path("tests/integration/test_decision_gates.py"): 525,
    Path("tests/integration/test_full_sdd.py"): 425,
}

V2_STAGE6_WORKER_TASKS = {
    "explore_request_profile",
    "explore_evidence_digest",
    "explore_outcome_synthesis",
    "purpose",
    "spec",
    "design",
    "tasks",
    "explorer_intake",
    "explorer_discovery",
    "explorer_decision",
    "explorer_artifact",
    "explorer_review",
    "explorer_distill",
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
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ast.Module(body=[], type_ignores=[])
    return ast.parse(source, filename=str(path))


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


def _warn_line_budget(report: Report, path: Path, budget: int, *, code: str) -> None:
    relative = rel(path)
    count = line_count(path)
    if count > budget:
        report.warn(
            f"{relative} has {count} lines; budget is {budget}",
            code=code,
            category="budget",
            path=relative,
            details={"lines": count, "budget": budget, "over_by": count - budget},
        )


def check_budgets(report: Report) -> None:
    for path in python_files(ROOT / "harness/ai_harness", ROOT / "harness/cli", ROOT / "harness/run.py", ROOT / "harness_v2"):
        relative = rel(path)
        budget = SOURCE_LINE_EXCEPTIONS.get(relative, SOURCE_LINE_BUDGET)
        _warn_line_budget(report, path, budget, code="line_budget.source")
    for path in python_files(ROOT / "tests/integration", ROOT / "test_v2/integration"):
        relative = rel(path)
        budget = INTEGRATION_LINE_EXCEPTIONS.get(relative, INTEGRATION_LINE_BUDGET)
        _warn_line_budget(report, path, budget, code="line_budget.integration")
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



def imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            prefix = "" if node.level == 0 else "." * node.level
            imported = f"{prefix}{module}"
            if imported:
                names.add(imported)
            for alias in node.names:
                if alias.name == "*":
                    continue
                if not imported:
                    names.add(alias.name)
                elif imported.endswith("."):
                    names.add(f"{imported}{alias.name}")
                else:
                    names.add(f"{imported}.{alias.name}")
    return names


def called_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def check_cli_frontend_boundaries(report: Report) -> None:
    commands = parse(ROOT / "harness/cli/commands.py")
    commands_forbidden_imports = {
        "harness.cli.console_app", "harness.cli.console_controller", "harness.cli.ui", "harness.cli.ui_primitives",
        ".console_app", ".console_controller", ".ui", ".ui_primitives",
    }
    commands_forbidden_calls = {"input", "_menu_prompt", "_text_prompt", "_line_prompt", "_multi_select_prompt", "_interactive_request", "_prompt_for_decision"}
    bad_imports = imported_names(commands) & commands_forbidden_imports
    bad_calls = called_names(commands) & commands_forbidden_calls
    if bad_imports or bad_calls:
        report.error(
            "harness/cli/commands.py must remain non-interactive CLI-only",
            code="cli_frontend.commands_boundary",
            category="boundary",
            path="harness/cli/commands.py",
            details={"imports": sorted(bad_imports), "calls": sorted(bad_calls)},
        )

    bootstrap = parse(ROOT / "harness/cli/bootstrap.py")
    bootstrap_forbidden = {
        "harness.cli.console", "harness.cli.console_actions", "harness.cli.console_app", "harness.cli.console_controller",
        "harness.cli.model_discovery", "harness.cli.model_prompts", "harness.cli.ui", "harness.cli.ui_primitives",
        ".console", ".console_actions", ".console_app", ".console_controller", ".model_discovery", ".model_prompts", ".ui", ".ui_primitives",
    }
    bad_bootstrap = imported_names(bootstrap) & bootstrap_forbidden
    if bad_bootstrap:
        report.error(
            "harness/cli/bootstrap.py must not import interactive frontend modules",
            code="cli_frontend.bootstrap_boundary",
            category="boundary",
            path="harness/cli/bootstrap.py",
            details={"imports": sorted(bad_bootstrap)},
        )

    console_app = parse(ROOT / "harness/cli/console_app.py")
    console_app_forbidden_imports = {
        "harness.cli.backend_client", "harness.cli.runtime", "harness.cli.ui", "harness.cli.ui_primitives",
        ".backend_client", ".runtime", ".ui", ".ui_primitives",
    }
    console_app_forbidden_calls = {"_run", "_unfinished_runs", "_completed_runs", "_decision_request", "_prompt_for_decision", "_menu_prompt", "_text_prompt", "_line_prompt"}
    bad_app_imports = imported_names(console_app) & console_app_forbidden_imports
    bad_app_calls = called_names(console_app) & console_app_forbidden_calls
    if bad_app_imports or bad_app_calls:
        report.error(
            "harness/cli/console_app.py must remain a thin UI composition root",
            code="cli_frontend.console_app_boundary",
            category="boundary",
            path="harness/cli/console_app.py",
            details={"imports": sorted(bad_app_imports), "calls": sorted(bad_app_calls)},
        )

    core_forbidden = {
        "harness.cli.backend_client", "harness.cli.runtime", "harness.cli.ui", "harness.cli.ui_primitives",
        ".backend_client", ".runtime", ".ui", ".ui_primitives", "..backend_client", "..runtime", "..ui", "..ui_primitives",
    }
    for name in ("action_plan.py", "effects.py", "messages.py", "model.py", "update.py", "view.py"):
        path = ROOT / "harness/cli/console" / name
        bad = imported_names(parse(path)) & core_forbidden
        if bad:
            report.error(
                f"harness/cli/console/{name} must stay pure MVU core",
                code="cli_frontend.mvu_core_boundary",
                category="boundary",
                path=rel(path),
                details={"imports": sorted(bad)},
            )

    cli_wrapper = (ROOT / "ai-harness").read_text(encoding="utf-8")
    ui_wrapper = (ROOT / "ai-harness-ui").read_text(encoding="utf-8")
    if "from harness.cli.commands import main" not in cli_wrapper or "from harness.cli import main" in cli_wrapper:
        report.error("ai-harness wrapper must target harness.cli.commands directly", code="cli_frontend.wrapper", category="boundary", path="ai-harness")
    if "from harness.cli.ui_main import main" not in ui_wrapper:
        report.error("ai-harness-ui wrapper must target harness.cli.ui_main", code="cli_frontend.wrapper", category="boundary", path="ai-harness-ui")


def _imports_with_prefix(imports: set[str], prefixes: set[str]) -> set[str]:
    return {
        module
        for module in imports
        for prefix in prefixes
        if module == prefix or module.startswith(f"{prefix}.")
    }


def check_v2_boundaries(report: Report) -> None:
    root = ROOT / "harness_v2"
    if not root.exists():
        return

    v1_forbidden = {"harness", "ai_harness"}
    for path in python_files(root):
        bad = _imports_with_prefix(imported_names(parse(path)), v1_forbidden)
        if bad:
            report.error(
                "v2 code must not import v1 harness modules",
                code="v2.v1_import_boundary",
                category="boundary",
                path=rel(path),
                details={"imports": sorted(bad)},
            )

    relative_forbidden = {
        f"{dots}{name}"
        for dots in (".", "..", "...", "....")
        for name in ("adapters", "hosts", "frontends")
    }
    domain_relative_forbidden = {
        f"{dots}{name}"
        for dots in (".", "..", "...", "....")
        for name in ("adapters", "hosts", "frontends", "application", "ports")
    }
    domain_forbidden = {
        "harness_v2.adapters",
        "harness_v2.hosts",
        "harness_v2.frontends",
        "harness_v2.backend.application",
        "harness_v2.backend.ports",
        *domain_relative_forbidden,
    }
    application_forbidden = {
        "harness_v2.adapters",
        "harness_v2.hosts",
        "harness_v2.frontends",
        *relative_forbidden,
    }
    ports_relative_forbidden = {
        f"{dots}{name}"
        for dots in (".", "..", "...", "....")
        for name in ("adapters", "hosts", "frontends", "application")
    }
    ports_forbidden = {
        "harness_v2.adapters",
        "harness_v2.hosts",
        "harness_v2.frontends",
        "harness_v2.backend.application",
        *ports_relative_forbidden,
    }
    adapters_forbidden = {
        "harness_v2.frontends",
        ".frontends",
        "..frontends",
        "...frontends",
        "....frontends",
    }
    frontends_forbidden = {
        "harness_v2.adapters",
        "harness_v2.backend.domain",
        "harness_v2.backend.ports",
        "harness_v2.backend.application",
        ".adapters",
        "..adapters",
        "...adapters",
        "....adapters",
        ".backend.domain",
        "..backend.domain",
        "...backend.domain",
        "....backend.domain",
        ".backend.ports",
        "..backend.ports",
        "...backend.ports",
        "....backend.ports",
        ".backend.application",
        "..backend.application",
        "...backend.application",
        "....backend.application",
    }
    frontends_allowed = {
        "harness_v2.backend.application.contracts",
        ".backend.application.contracts",
        "..backend.application.contracts",
        "...backend.application.contracts",
        "....backend.application.contracts",
    }
    hosts_forbidden = {
        "harness_v2.frontends",
        ".frontends",
        "..frontends",
        "...frontends",
        "....frontends",
    }

    boundary_checks = (
        (
            root / "backend" / "domain",
            domain_forbidden,
            "v2.domain_boundary",
            "v2 domain must not import adapters, hosts, or frontends",
        ),
        (
            root / "backend" / "application",
            application_forbidden,
            "v2.application_boundary",
            "v2 application must not import adapters, hosts, or frontends",
        ),
        (
            root / "backend" / "ports",
            ports_forbidden,
            "v2.ports_boundary",
            "v2 ports must not import adapters, hosts, frontends, or application services",
        ),
        (
            root / "adapters",
            adapters_forbidden,
            "v2.adapters_boundary",
            "v2 adapters must not import frontends",
        ),
        (
            root / "frontends",
            frontends_forbidden,
            "v2.frontends_boundary",
            "v2 frontends must not import outbound adapters",
        ),
        (
            root / "hosts",
            hosts_forbidden,
            "v2.hosts_boundary",
            "v2 hosts must not import frontends",
        ),
    )

    for folder, forbidden, code, message in boundary_checks:
        for path in python_files(folder):
            tree = parse(path)
            imports = imported_names(tree)
            bad = _imports_with_prefix(imports, forbidden)
            if code == "v2.frontends_boundary":
                allowed = _imports_with_prefix(imports, frontends_allowed)
                bad = {module for module in bad if module not in allowed}
            if bad:
                report.error(
                    message,
                    code=code,
                    category="boundary",
                    path=rel(path),
                    details={"imports": sorted(bad)},
                )
            if code == "v2.frontends_boundary":
                filesystem_calls = _frontend_filesystem_calls(tree)
                if filesystem_calls:
                    report.error(
                        "v2 frontends must not access runtime, state, or artifact files directly",
                        code="v2.frontends_filesystem_boundary",
                        category="boundary",
                        path=rel(path),
                        details={"calls": sorted(filesystem_calls)},
                    )



_FRONTEND_FILESYSTEM_CALLS = {
    "open",
    "read_text",
    "write_text",
    "read_bytes",
    "write_bytes",
    "glob",
    "rglob",
    "iterdir",
    "unlink",
    "mkdir",
}


def _frontend_filesystem_calls(tree: ast.Module) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            calls.add("open")
        elif isinstance(node.func, ast.Attribute) and node.func.attr in _FRONTEND_FILESYSTEM_CALLS:
            calls.add(node.func.attr)
    return calls



def _model_adapter_shell_findings(tree: ast.Module) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    subprocess_calls = {"run", "Popen", "call", "check_call", "check_output"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_subprocess_call = False
        if isinstance(func, ast.Attribute) and func.attr in subprocess_calls:
            if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                is_subprocess_call = True
        if not is_subprocess_call:
            continue
        for keyword in node.keywords:
            if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                findings.append({"call": func.attr, "reason": "shell=True"})
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            findings.append({"call": func.attr, "reason": "string command"})
    return findings



def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = [func.attr]
        value = func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _string_constants(node: ast.AST) -> list[str]:
    return [item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str)]


def _v2_backend_external_effect_findings(tree: ast.Module) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    path_names = {"Path"}
    path_vars: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
            for alias in node.names:
                if alias.name == "Path":
                    path_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _call_name(node.value) in path_names:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        path_vars.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and isinstance(node.value, ast.Call):
            if _call_name(node.value) in path_names:
                path_vars.add(node.target.id)

    path_effect_attrs = {"read_text", "write_text", "read_bytes", "write_bytes", "open"}
    path_mutation_attrs = {"unlink", "mkdir", "rmdir", "rename", "replace", "touch", "chmod"}
    path_traversal_attrs = {"glob", "rglob", "iterdir"}
    os_effects = {"os.remove", "os.unlink", "os.mkdir", "os.makedirs", "os.rmdir", "os.rename", "os.replace"}
    shutil_effects = {"shutil.rmtree", "shutil.copy", "shutil.copy2", "shutil.copytree", "shutil.move"}
    subprocess_effects = {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output"}

    def path_call_kind(call: ast.Call) -> str | None:
        if not isinstance(call.func, ast.Attribute):
            return None
        attr = call.func.attr
        value = call.func.value
        is_path_value = False
        if isinstance(value, ast.Call) and _call_name(value) in path_names:
            is_path_value = True
        elif isinstance(value, ast.Name) and value.id in path_vars:
            is_path_value = True
        if not is_path_value:
            return None
        if attr in path_effect_attrs:
            return "filesystem access must be behind a port/adapter"
        if attr in path_mutation_attrs:
            return "filesystem mutation must be behind a port/adapter"
        if attr in path_traversal_attrs:
            return "filesystem traversal must be behind a port/adapter"
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in subprocess_effects:
            findings.append({"call": name, "reason": "subprocess must be behind a port/adapter"})
            if any(part == "git" or part.startswith("git ") for part in _string_constants(node)):
                findings.append({"call": name, "reason": "git execution must be behind a port/adapter"})
        elif name == "os.system":
            findings.append({"call": name, "reason": "shell execution must be behind a port/adapter"})
        elif name in os_effects or name in shutil_effects:
            findings.append({"call": name, "reason": "filesystem mutation must be behind a port/adapter"})
        elif name == "Path.cwd" or any(name == f"{path_name}.cwd" for path_name in path_names):
            findings.append({"call": name, "reason": "working directory must be injected by host/runtime"})
        elif name == "open":
            findings.append({"call": name, "reason": "filesystem access must be behind a port/adapter"})
        else:
            reason = path_call_kind(node)
            if reason is not None:
                findings.append({"call": name, "reason": reason})
    return findings


def check_v2_backend_external_effects(report: Report) -> None:
    for root in (ROOT / "harness_v2" / "backend" / "domain", ROOT / "harness_v2" / "backend" / "application"):
        if not root.exists():
            continue
        for path in python_files(root):
            findings = _v2_backend_external_effect_findings(parse(path))
            if findings:
                report.error(
                    "v2 backend must not perform direct filesystem, subprocess, or git effects",
                    code="v2.backend_external_effect_boundary",
                    category="boundary",
                    path=rel(path),
                    details={"findings": findings},
                )

def check_v2_model_provider_execution(report: Report) -> None:
    root = ROOT / "harness_v2" / "adapters" / "models"
    if not root.exists():
        return
    for path in python_files(root):
        findings = _model_adapter_shell_findings(parse(path))
        if findings:
            report.error(
                "v2 model provider adapters must execute argv lists without shell interpretation",
                code="v2.model_provider_shell_boundary",
                category="boundary",
                path=rel(path),
                details={"findings": findings},
            )


def check_v2_domain_test_boundaries(report: Report) -> None:
    root = ROOT / "test_v2" / "unit"
    if not root.exists():
        return

    forbidden_roots = {"harness", "ai_harness", "harness_v2"}
    allowed_v2_domain = {"harness_v2.backend.domain"}
    for path in sorted(root.glob("test_domain*.py")):
        imports = imported_names(parse(path))
        bad = _imports_with_prefix(imports, forbidden_roots)
        bad -= _imports_with_prefix(imports, allowed_v2_domain)
        if bad:
            report.error(
                "v2 domain unit tests must import only v2 domain modules from harness_v2",
                code="v2.domain_tests_boundary",
                category="boundary",
                path=rel(path),
                details={"imports": sorted(bad)},
            )


def check_v2_worker_resources(report: Report) -> None:
    root = ROOT / "harness_v2"
    if not root.exists():
        return
    for task_id in sorted(V2_STAGE6_WORKER_TASKS):
        expected = (
            root / "workers" / f"{task_id}.md",
            root / "prompts" / f"{task_id}.md",
            root / "capabilities" / f"{task_id}.json",
        )
        missing = [rel(path) for path in expected if not path.is_file()]
        empty = [rel(path) for path in expected[:2] if path.is_file() and not path.read_text(encoding="utf-8").strip()]
        if missing or empty:
            report.error(
                "v2 Stage 6 worker tasks require markdown and capability resources",
                code="v2.worker_resources",
                category="boundary",
                path="harness_v2",
                details={"task_id": task_id, "missing": [str(path) for path in missing], "empty": [str(path) for path in empty]},
            )


def check_v2_runtime_test_double_names(report: Report) -> None:
    root = ROOT / "harness_v2"
    if not root.exists():
        return
    forbidden_filenames = {"fake.py", "stub.py", "skeleton.py"}
    forbidden_prefixes = ("Fake", "Stub")
    forbidden_suffixes = ("Skeleton",)
    for path in python_files(root):
        if path.name in forbidden_filenames:
            report.error(
                "v2 runtime code must not keep fake, stub, or skeleton modules",
                code="v2.runtime_test_double_names",
                category="boundary",
                path=rel(path),
                details={"filename": path.name},
            )
        tree = parse(path)
        test_imports = _imports_with_prefix(imported_names(tree), {"test_v2"})
        if test_imports:
            report.error(
                "v2 runtime code must not import test support",
                code="v2.runtime_test_support_import",
                category="boundary",
                path=rel(path),
                details={"imports": sorted(test_imports)},
            )
        bad_classes = sorted(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and (node.name.startswith(forbidden_prefixes) or node.name.endswith(forbidden_suffixes))
        )
        if bad_classes:
            report.error(
                "v2 runtime code must not define fake, stub, or skeleton classes",
                code="v2.runtime_test_double_names",
                category="boundary",
                path=rel(path),
                details={"classes": bad_classes},
            )



def check_v2_bundle_phase_schema(report: Report) -> None:
    root = ROOT / "harness_v2"
    if not root.exists():
        return
    forbidden_tokens = {
        "RunStrategy",
        "WorkflowName",
        "InternalPhaseName",
        "LifecycleGraph",
        "PhaseRetryStarted",
        "origin_phase",
        "BundlePlan",
        "BundleOrchestrator",
        "RunService",
        "BundleExecutionResult",
        "PhaseHandlerRegistry",
        "default_bundle_registry",
        "default_phase_handler_registry",
        "_tdd_noop",
    }
    for path in python_files(root):
        source = path.read_text(encoding="utf-8")
        found = sorted(token for token in forbidden_tokens if token in source)
        if found:
            report.error(
                "v2 runtime must use bundle/phase composition terminology only",
                code="v2.bundle_phase_schema_legacy_names",
                category="boundary",
                path=rel(path),
                details={"tokens": found},
            )
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from harness_v2.backend.domain import bundle_catalog
        from harness_v2.backend.domain.lifecycle import BundleName, BundleRef, PhaseRef, bundle_spec
    except Exception as exc:
        report.error(
            "v2 bundle/phase schema must be importable",
            code="v2.bundle_phase_schema_import",
            category="boundary",
            details={"error": str(exc)},
        )
        return
    sdd = bundle_spec(BundleName.SDD_BUNDLE)
    if not sdd.children or not all(isinstance(child, BundleRef) for child in sdd.children):
        report.error(
            "SDD_BUNDLE must compose other bundles, not executable phases directly",
            code="v2.sdd_bundle_composition",
            category="boundary",
            path="harness_v2/backend/domain/lifecycle.py",
        )
    for bundle in BundleName:
        spec = bundle_spec(bundle)
        if not spec.children:
            report.error(
                "v2 bundle specs must declare children",
                code="v2.empty_bundle_spec",
                category="boundary",
                path="harness_v2/backend/domain/lifecycle.py",
                details={"bundle": bundle.value},
            )
        for child in spec.children:
            if not isinstance(child, (BundleRef, PhaseRef)):
                report.error(
                    "v2 bundle children must be BundleRef or PhaseRef",
                    code="v2.invalid_bundle_child",
                    category="boundary",
                    path="harness_v2/backend/domain/lifecycle.py",
                    details={"bundle": bundle.value, "child_type": type(child).__name__},
                )
    phase_values = [step.phase_name.value for step in bundle_catalog.linearize_bundle(BundleName.SDD_BUNDLE)]
    duplicate_phases = {phase for phase in phase_values if phase_values.count(phase) > 1}
    if duplicate_phases - {"VALIDATE_JSON"}:
        report.error(
            "SDD_BUNDLE executable phases may only repeat for VALIDATE_JSON",
            code="v2.duplicate_executable_phases",
            category="boundary",
            path="harness_v2/backend/domain/lifecycle.py",
            details={"duplicate_phases": sorted(duplicate_phases)},
        )

def run_checks() -> Report:
    report = Report()
    check_graph_contract(report)
    check_dispatcher_contract(report)
    check_phase_resources(report)
    check_import_boundaries(report)
    check_state_mutation(report)
    check_budgets(report)
    check_cli_frontend_boundaries(report)
    check_v2_boundaries(report)
    check_v2_runtime_test_double_names(report)
    check_v2_bundle_phase_schema(report)
    check_v2_model_provider_execution(report)
    check_v2_backend_external_effects(report)
    check_v2_worker_resources(report)
    check_v2_domain_test_boundaries(report)
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
