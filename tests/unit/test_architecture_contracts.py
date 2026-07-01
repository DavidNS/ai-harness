from __future__ import annotations

import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))

import check_architecture
from ai_harness.errors import ValidationError
from ai_harness.orchestrator.phase_executor import PhaseExecutor


class ArchitectureContractTests(unittest.TestCase):
    def test_architecture_checker_has_no_blocking_errors(self) -> None:
        report = check_architecture.run_checks()
        self.assertEqual([], report.errors)

    def test_architecture_checker_exposes_structured_findings(self) -> None:
        report = check_architecture.run_checks()
        payload = report.to_dict()

        self.assertEqual("passed", payload["status"])
        self.assertEqual(0, payload["error_count"])
        self.assertEqual(len(report.warnings), payload["warning_count"])
        self.assertEqual(len(report.findings), len(payload["findings"]))
        self.assertTrue(all("code" in finding for finding in payload["findings"]))

    def test_architecture_checker_structures_budget_warnings(self) -> None:
        report = check_architecture.run_checks()
        budget_findings = [
            finding
            for finding in report.findings
            if finding.code in {"line_budget.source", "line_budget.integration"}
        ]

        self.assertTrue(budget_findings)
        self.assertTrue(all(finding.category == "budget" for finding in budget_findings))
        self.assertTrue(all("lines" in finding.details for finding in budget_findings))
        self.assertTrue(all("budget" in finding.details for finding in budget_findings))
        self.assertTrue(all("over_by" in finding.details for finding in budget_findings))

    def test_architecture_checker_summary_rendering(self) -> None:
        report = check_architecture.run_checks()

        self.assertEqual(
            f"Architecture check passed: {len(report.warnings)} warning(s)",
            check_architecture.render_summary(report),
        )

    def _v2_boundary_codes_for(self, relative_path: str, source: str) -> set[str]:
        path = ROOT / relative_path
        path.write_text(source, encoding="utf-8")
        try:
            report = check_architecture.Report()
            check_architecture.check_v2_boundaries(report)
            check_architecture.check_v2_domain_test_boundaries(report)
            return {finding.code for finding in report.findings}
        finally:
            path.unlink(missing_ok=True)

    def test_v2_boundary_checker_rejects_domain_importing_adapters_absolute(self) -> None:
        codes = self._v2_boundary_codes_for(
            "harness_v2/backend/domain/_bad_boundary_fixture.py",
            "from harness_v2.adapters import storage\n",
        )

        self.assertIn("v2.domain_boundary", codes)

    def test_v2_boundary_checker_rejects_domain_importing_adapters_relative(self) -> None:
        codes = self._v2_boundary_codes_for(
            "harness_v2/backend/domain/_bad_boundary_fixture.py",
            "from ... import adapters\n",
        )

        self.assertIn("v2.domain_boundary", codes)

    def test_v2_boundary_checker_rejects_frontend_importing_adapters(self) -> None:
        codes = self._v2_boundary_codes_for(
            "harness_v2/frontends/_bad_boundary_fixture.py",
            "from harness_v2.adapters import storage\n",
        )

        self.assertIn("v2.frontends_boundary", codes)

    def test_v2_boundary_checker_rejects_any_v1_import(self) -> None:
        codes = self._v2_boundary_codes_for(
            "harness_v2/backend/application/_bad_boundary_fixture.py",
            "from ai_harness.orchestrator import lifecycle\n",
        )

        self.assertIn("v2.v1_import_boundary", codes)

    def test_v2_boundary_checker_rejects_application_importing_adapters(self) -> None:
        codes = self._v2_boundary_codes_for(
            "harness_v2/backend/application/_bad_boundary_fixture.py",
            "from harness_v2.adapters import storage\n",
        )

        self.assertIn("v2.application_boundary", codes)

    def test_v2_boundary_checker_rejects_adapters_importing_frontends(self) -> None:
        codes = self._v2_boundary_codes_for(
            "harness_v2/adapters/_bad_boundary_fixture.py",
            "from harness_v2.frontends import cli\n",
        )

        self.assertIn("v2.adapters_boundary", codes)

    def test_v2_boundary_checker_rejects_hosts_importing_frontends(self) -> None:
        codes = self._v2_boundary_codes_for(
            "harness_v2/hosts/_bad_boundary_fixture.py",
            "from harness_v2.frontends import cli\n",
        )

        self.assertIn("v2.hosts_boundary", codes)



    def test_v2_domain_unit_tests_reject_application_imports(self) -> None:
        codes = self._v2_boundary_codes_for(
            "test_v2/unit/test_domain_bad_boundary_fixture.py",
            "from harness_v2.backend.application import contracts\n",
        )

        self.assertIn("v2.domain_tests_boundary", codes)

    def test_v2_domain_unit_tests_reject_hosts_frontends_adapters_and_v1_imports(self) -> None:
        cases = (
            "from harness_v2.hosts.in_process import host\n",
            "from harness_v2.frontends import cli\n",
            "from harness_v2.adapters import storage\n",
            "from ai_harness.models import RunState\n",
        )
        for source in cases:
            with self.subTest(source=source):
                codes = self._v2_boundary_codes_for(
                    "test_v2/unit/test_domain_bad_boundary_fixture.py",
                    source,
                )
                self.assertIn("v2.domain_tests_boundary", codes)

    def test_cli_commands_module_has_no_interactive_ui_dependencies(self) -> None:
        path = ROOT / "harness" / "cli" / "commands.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {
            "harness.cli.console_app",
            "harness.cli.console_controller",
            "harness.cli.ui",
            "harness.cli.ui_primitives",
            ".console_app",
            ".console_controller",
            ".ui",
            ".ui_primitives",
        }
        forbidden_calls = {
            "input",
            "_menu_prompt",
            "_text_prompt",
            "_line_prompt",
            "_multi_select_prompt",
            "_interactive_request",
            "_prompt_for_decision",
        }

        imports: set[str] = set()
        calls: set[str] = set()
        assigned_internal_state = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.add(module if node.level == 0 else "." * node.level + module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "_interactive_ui":
                        assigned_internal_state = True
                    if isinstance(target, ast.Name) and target.id == "_interactive_ui":
                        assigned_internal_state = True

        self.assertTrue(imports.isdisjoint(forbidden_imports), imports & forbidden_imports)
        self.assertTrue(calls.isdisjoint(forbidden_calls), calls & forbidden_calls)
        self.assertFalse(assigned_internal_state)


    def test_bootstrap_module_has_no_interactive_ui_dependencies(self) -> None:
        path = ROOT / "harness" / "cli" / "bootstrap.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {
            "harness.cli.console",
            "harness.cli.console_actions",
            "harness.cli.console_app",
            "harness.cli.console_controller",
            "harness.cli.model_discovery",
            "harness.cli.model_prompts",
            "harness.cli.ui",
            "harness.cli.ui_primitives",
            ".console",
            ".console_actions",
            ".console_app",
            ".console_controller",
            ".model_discovery",
            ".model_prompts",
            ".ui",
            ".ui_primitives",
        }
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.add(module if node.level == 0 else "." * node.level + module)
        self.assertTrue(imports.isdisjoint(forbidden_imports), imports & forbidden_imports)

    def test_cli_import_does_not_load_console_ui_transitively(self) -> None:
        script = """
import json
import sys
import harness.cli.commands
forbidden = sorted(
    name
    for name in sys.modules
    if name in {
        'harness.cli.ui',
        'harness.cli.ui_primitives',
        'harness.cli.model_discovery',
        'harness.cli.model_prompts',
        'termios',
    } or name.startswith('harness.cli.console')
)
print(json.dumps(forbidden))
"""
        env = dict(os.environ)
        paths = [str(ROOT / "harness"), str(ROOT)]
        env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            check=True,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual("[]", result.stdout.strip())


    def test_launcher_wrappers_target_separate_entrypoints(self) -> None:
        cli_wrapper = (ROOT / "ai-harness").read_text(encoding="utf-8")
        ui_wrapper = (ROOT / "ai-harness-ui").read_text(encoding="utf-8")

        self.assertIn("from harness.cli.commands import main", cli_wrapper)
        self.assertIn("from harness.cli.ui_main import main", ui_wrapper)
        self.assertNotIn("from harness.cli import main", cli_wrapper)

    def test_console_mvu_core_has_no_terminal_or_backend_dependencies(self) -> None:
        forbidden_imports = {
            "harness.cli.backend_client",
            "harness.cli.runtime",
            "harness.cli.ui",
            "harness.cli.ui_primitives",
            ".backend_client",
            ".runtime",
            ".ui",
            ".ui_primitives",
            "..backend_client",
            "..runtime",
            "..ui",
            "..ui_primitives",
        }
        core_files = [
            ROOT / "harness" / "cli" / "console" / name
            for name in ("action_plan.py", "effects.py", "messages.py", "model.py", "update.py", "view.py")
        ]
        for path in core_files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports.add(module if node.level == 0 else "." * node.level + module)
            self.assertTrue(imports.isdisjoint(forbidden_imports), (path.name, imports & forbidden_imports))


    def test_shared_parser_keeps_ui_only_options_out_of_cli_default(self) -> None:
        from harness.cli.bootstrap import _parser

        cli_options = {option for action in _parser()._actions for option in action.option_strings}
        ui_options = {option for action in _parser(include_ui_options=True)._actions for option in action.option_strings}

        self.assertNotIn("--skip-warnings", cli_options)
        self.assertIn("--skip-warnings", ui_options)

    def test_phase_executor_fails_closed_for_unknown_phase(self) -> None:
        with self.assertRaises(ValidationError):
            PhaseExecutor({}).execute("MISSING_PHASE")

    def test_phase_executor_runs_known_phase(self) -> None:
        calls: list[str] = []
        PhaseExecutor({"KNOWN": lambda: calls.append("called")}).execute("KNOWN")
        self.assertEqual(["called"], calls)

    def test_dispatcher_covers_graph_phases(self) -> None:
        dispatched = check_architecture.dispatcher_phases()
        graph_phases = {
            check_architecture.phase_value(phase)
            for graph in check_architecture.GRAPHS.values()
            for phase in graph
        }
        missing = graph_phases - dispatched - {"SNAPSHOTTING", "COMPLETED"}
        self.assertEqual(set(), missing)


if __name__ == "__main__":
    unittest.main()
