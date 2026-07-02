from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness_v2"


def python_files(path: Path) -> list[Path]:
    return sorted(item for item in path.rglob("*.py") if item.name != "__init__.py")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def assert_no_import_prefixes(test: unittest.TestCase, base: Path, forbidden: tuple[str, ...]) -> None:
    for path in python_files(base):
        rel = path.relative_to(ROOT)
        for module in imported_modules(path):
            with test.subTest(file=str(rel), module=module):
                test.assertFalse(
                    any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden),
                    f"{rel} imports forbidden module {module}",
                )


class ArchitectureGuardrailTests(unittest.TestCase):
    def test_domain_imports_no_outer_layers_or_ports(self) -> None:
        assert_no_import_prefixes(
            self,
            HARNESS / "backend" / "domain",
            (
                "harness_v2.backend.application",
                "harness_v2.backend.ports",
                "harness_v2.adapters",
                "harness_v2.hosts",
                "harness_v2.frontends",
            ),
        )

    def test_application_imports_no_adapters_hosts_or_frontends(self) -> None:
        assert_no_import_prefixes(
            self,
            HARNESS / "backend" / "application",
            (
                "harness_v2.adapters",
                "harness_v2.hosts",
                "harness_v2.frontends",
            ),
        )

    def test_frontends_use_only_contracts_and_host_boundary(self) -> None:
        for path in python_files(HARNESS / "frontends"):
            rel = path.relative_to(ROOT)
            for module in imported_modules(path):
                if not module.startswith("harness_v2."):
                    continue
                allowed = (
                    module == "harness_v2.backend.application.contracts"
                    or module.startswith("harness_v2.hosts.")
                    or module.startswith("harness_v2.frontends.")
                )
                with self.subTest(file=str(rel), module=module):
                    self.assertTrue(allowed, f"{rel} imports non-frontend boundary module {module}")

    def test_phases_do_not_mutate_authoritative_state_or_decisions_directly(self) -> None:
        forbidden_attrs = {"state_store", "artifact_store", "decision_service"}
        for path in python_files(HARNESS / "backend" / "application" / "phases"):
            rel = path.relative_to(ROOT)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                    with self.subTest(file=str(rel), attr=node.attr, line=node.lineno):
                        self.fail(f"{rel}:{node.lineno} accesses PhaseExecutionContext.{node.attr} directly")

    def test_application_bundles_do_not_contain_phase_implementation_modules(self) -> None:
        bundles_dir = HARNESS / "backend" / "application" / "bundles"
        if not bundles_dir.exists():
            return
        leftovers = sorted(path.name for path in bundles_dir.glob("*_phases.py"))
        self.assertEqual([], leftovers)

    def test_sdd_spec_and_design_artifacts_are_json_not_markdown(self) -> None:
        phase_root = HARNESS / "backend" / "application" / "phases"
        checked = (
            phase_root / "spec_draft.py",
            phase_root / "spec_handoff.py",
            phase_root / "design_draft.py",
            phase_root / "design_handoff.py",
            phase_root / "tasks_draft.py",
        )
        for path in checked:
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertNotIn("spec.md", source)
                self.assertNotIn("design.md", source)

    def test_private_harness_v2_helpers_are_referenced(self) -> None:
        checked = python_files(HARNESS)
        references: set[str] = set()
        for path in python_files(HARNESS):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    references.add(node.id)
                elif isinstance(node, ast.Attribute):
                    references.add(node.attr)

        dead_helpers: list[str] = []
        for path in checked:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not node.name.startswith("_") or node.name.startswith("__"):
                    continue
                if node.name not in references:
                    rel = path.relative_to(ROOT)
                    dead_helpers.append(f"{rel}:{node.lineno} {node.name}")

        self.assertEqual([], dead_helpers)


if __name__ == "__main__":
    unittest.main()
