"""Domain classifiers for repository paths and observation types.

Pure functions — no I/O, no harness state, no side effects.
Previously staticmethods scattered across WorkerExchange and
ExplorerFlowMixin; extracted here so RepositoryScanner and other
future collaborators can import them without touching the mixin chain.
"""
from __future__ import annotations

from ..contracts.enums import ArtifactKind
from ..text.markdown import markdown_section as _markdown_section


def explorer_kind(candidate: str) -> ArtifactKind:
    """Classify an explorer artifact by its content shape."""
    first_line = candidate.replace("\r\n", "\n").splitlines()[0].strip() if candidate else ""
    outcome = _markdown_section(candidate, "Outcome").casefold()
    if first_line == "# Existing Functionality v1" or "existing-functionality" in outcome or "already exists" in outcome:
        return ArtifactKind.EXISTING_FUNCTIONALITY
    if first_line in {"# Improvement Explorer v1", "# Improvement Analysis v1"} or first_line.startswith("# Improvement:"):
        return ArtifactKind.IMPROVEMENT
    if "not-worth-it" in outcome or "not worth" in outcome or "bullshit" in outcome:
        return ArtifactKind.BULLSHIT
    return ArtifactKind.LIMITATION


def repository_observation_kind(relative: str) -> str:
    """Classify a relative file path into a broad category."""
    if relative.startswith("tests/") or "/tests/" in relative:
        return "test"
    if "/prompts/" in relative or relative.startswith("prompts/"):
        return "prompt"
    if "/workers/" in relative or relative.startswith("workers/"):
        return "worker"
    if relative.startswith("docs/explorer/"):
        return "explorer_doc"
    if relative.endswith(".py"):
        return "source"
    return "path"
