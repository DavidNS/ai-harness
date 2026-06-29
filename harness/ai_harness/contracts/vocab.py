"""Domain vocabulary lists used in quality gates and classification.

Previously inlined as module-level tuples in analysis_quality.py and
phase_execution.py. Centralised here so they can be updated in one place
and are discoverable without reading the orchestrator internals.
"""
from __future__ import annotations

# Evidence phrases considered too generic to count as concrete evidence.
GENERIC_EVIDENCE_PHRASES: tuple[str, ...] = (
    "evidence exists",
    "explorer found",
    "explorer identified",
    "repository evidence",
    "required by test",
    "the idea is viable",
    "this improvement is viable",
)

# Terms that indicate a bundle spans too broad a surface (catch-all detector).
BROAD_SURFACE_TERMS: tuple[str, ...] = (
    "explorer gate", "canonical", "controller", "documentation", "manifest", "orchestration",
    "orchestrator", "prompt", "publication", "routing", "state", "storage", "test", "worker",
)

# Phrases in an improvement title/problem that signal a catch-all bundle.
CATCH_ALL_BUNDLE_PHRASES: tuple[str, ...] = (
    "catch-all",
    "catch all",
    "everything else",
    "all remaining",
    "whole harness",
    "entire harness",
    "multiple unrelated",
    "unrelated surfaces",
)

# Expected section aliases for structured acceptance criteria.
ACCEPTANCE_CRITERIA_EXPECTED_ALIASES: tuple[tuple[str, ...], ...] = (
    ("given", "when", "context", "scenario", "dado", "si", "when_condition"),
    ("then", "expected", "outcome", "result", "esperado", "resultado"),
    ("verify", "verification", "evidence", "check", "test", "validacion", "comprobacion"),
)

# Terms that indicate an impossible outcome is due to infrastructure/tooling,
# not a genuine analysis deadlock (from phase_execution.py).
INFRASTRUCTURE_TERMS: tuple[str, ...] = (
    "access denied", "authentication", "auth failed", "bwrap", "cannot inspect",
    "cannot read", "command failed", "could not inspect", "could not read",
    "failed before execution", "permission", "provider", "sandbox", "timed out",
    "timeout", "tooling", "unavailable evidence", "worker environment",
)
