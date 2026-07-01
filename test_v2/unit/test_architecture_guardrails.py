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

    def test_bundles_do_not_mutate_authoritative_state_or_decisions_directly(self) -> None:
        forbidden_attrs = {"state_store", "artifact_store", "decision_service"}
        for path in python_files(HARNESS / "backend" / "application" / "bundles"):
            rel = path.relative_to(ROOT)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                    with self.subTest(file=str(rel), attr=node.attr, line=node.lineno):
                        self.fail(f"{rel}:{node.lineno} accesses BundleContext.{node.attr} directly")



if __name__ == "__main__":
    unittest.main()
