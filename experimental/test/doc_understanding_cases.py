"""Shared cases for experimental architecture-document understanding checks."""

from __future__ import annotations

from dataclasses import dataclass


READING_GUIDE = (
    "Use this document as a system map, not as a low-level implementation "
    "contract. Prefer local domain docs, tests, and source files for detailed "
    "code changes."
)


@dataclass(frozen=True, slots=True)
class DocUnderstandingCase:
    """One prompt and deterministic scoring expectations for live doc evals."""

    case_id: str
    prompt: str
    required_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...] = ()


CASES: tuple[DocUnderstandingCase, ...] = (
    DocUnderstandingCase(
        case_id="adapter-boundary",
        prompt=(
            "Using ARCHITECTURE.md as an overview, explain where a new backend "
            "adapter should fit and what boundary it should preserve."
        ),
        required_terms=("backend", "adapter", "hexagonal", "orchestration"),
        forbidden_terms=("database migration", "REST endpoint schema"),
    ),
    DocUnderstandingCase(
        case_id="knowledge-release-fit",
        prompt=(
            "Using ARCHITECTURE.md as an overview, explain how knowledge "
            "extraction relates to the release lifecycle."
        ),
        required_terms=("knowledge", "source of truth", "release", "artifacts"),
        forbidden_terms=("Jira", "project-management"),
    ),
    DocUnderstandingCase(
        case_id="command-frontend",
        prompt=(
            "Using ARCHITECTURE.md as an overview, describe how to approach a "
            "new command in the frontend console."
        ),
        required_terms=("command", "Model-View-Update", "intent", "effects"),
        forbidden_terms=("React", "browser DOM"),
    ),
    DocUnderstandingCase(
        case_id="domain-locality",
        prompt=(
            "Using ARCHITECTURE.md as an overview, decide whether a change "
            "should stay inside one domain or become cross-cutting."
        ),
        required_terms=("domain", "ownership", "context", "validation"),
        forbidden_terms=("global refactor", "rewrite everything"),
    ),
)


def case_ids() -> tuple[str, ...]:
    return tuple(case.case_id for case in CASES)
