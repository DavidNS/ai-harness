"""ImprovementQualityGate — pure validation for compact improvement artifacts.

All methods are stateless and take only the data they inspect. Repository
observations are passed explicitly so this class has no dependency on
RunContext or any mixin.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from ..contracts.vocab import (
    ACCEPTANCE_CRITERIA_EXPECTED_ALIASES,
    BROAD_SURFACE_TERMS,
    CATCH_ALL_BUNDLE_PHRASES,
    GENERIC_EVIDENCE_PHRASES,
)
from ..control_outputs import ExplorerBundleEntry
from ..errors import HarnessError
from ..text.markdown import compact_lines, markdown_section, strip_code_block
from ..text.normalize import normalize_key, normalized_statement


class ImprovementQualityGate:
    """Validates and inspects compact improvement artifacts.

    Stateless — one module-level instance is enough.
    """

    # ------------------------------------------------------------------ #
    # Simple predicates                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def is_compact_improvement(content: str) -> bool:
        first_line = content.replace("\r\n", "\n").splitlines()[0].strip() if content else ""
        return first_line.startswith("# Improvement:")

    @staticmethod
    def is_generic_evidence(evidence: str) -> bool:
        text = " ".join(evidence.casefold().split()).strip(". ")
        if len(text) < 12 or text in {"none", "n/a", "not applicable"}:
            return True
        has_concrete_reference = any(marker in evidence for marker in ("/", "`", ".py", ".md", ".json"))
        return not has_concrete_reference and any(phrase in text for phrase in GENERIC_EVIDENCE_PHRASES)

    @staticmethod
    def criterion_is_observable(line: str) -> bool:
        text = " ".join(line.casefold().split()).strip()
        if not text or len(text.split()) < 4:
            return False
        if "desired behavior" in text or "described behavior" in text:
            return False
        return True

    @staticmethod
    def requires_scope_justification(content: str) -> bool:
        text = content.casefold()
        if sum(1 for term in BROAD_SURFACE_TERMS if term in text) < 5:
            return False
        return not any(
            phrase in text
            for phrase in (
                "scope justification",
                "bounded because",
                "single artifact is bounded",
                "single improvement is bounded",
            )
        )

    @staticmethod
    def is_unfocused_bundle_child(content: str, entry: ExplorerBundleEntry) -> bool:
        text = f"{entry.entry_id} {entry.title} {content}".casefold()
        return any(phrase in text for phrase in CATCH_ALL_BUNDLE_PHRASES)

    # ------------------------------------------------------------------ #
    # Acceptance-criteria parsing                                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def acceptance_value_for(cls, criteria: Mapping[str, object], aliases: Sequence[str]) -> str:
        alias_set = {normalize_key(alias) for alias in aliases}
        for key, value in criteria.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            if normalize_key(key) in alias_set and value.strip():
                return value.strip()
        return ""

    def parse_structured_acceptance_criteria(self, section: str) -> tuple[dict[str, str], ...] | None:
        text = strip_code_block(section).strip()
        if not text.startswith("[") or not text.endswith("]"):
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HarnessError(
                "compact improvement acceptance criteria must be a valid JSON array or a list of bullets"
            ) from exc
        if not isinstance(payload, list):
            raise HarnessError("compact improvement acceptance criteria must be a JSON array")
        if not payload:
            raise HarnessError("compact improvement acceptance criteria must contain at least one item")
        if all(isinstance(item, str) for item in payload):
            return None
        parsed: list[dict[str, str]] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, Mapping):
                raise HarnessError(f"compact improvement acceptance criteria item {index} must be an object")
            then = self.acceptance_value_for(item, ACCEPTANCE_CRITERIA_EXPECTED_ALIASES[1])
            verify = self.acceptance_value_for(item, ACCEPTANCE_CRITERIA_EXPECTED_ALIASES[2])
            if not then or not verify:
                raise HarnessError(
                    f"compact improvement acceptance criteria item {index} must include both an outcome and verification field"
                )
            parsed.append({
                "given": self.acceptance_value_for(item, ACCEPTANCE_CRITERIA_EXPECTED_ALIASES[0]),
                "then": then,
                "verify": verify,
            })
        return tuple(parsed)

    def validate_acceptance_criteria(self, section: str) -> bool:
        structured = self.parse_structured_acceptance_criteria(section)
        if structured is not None:
            return bool(structured)
        lines = compact_lines(section)
        if not lines:
            return False
        return any(self.criterion_is_observable(line) for line in lines)

    # ------------------------------------------------------------------ #
    # Repository-observation evidence checks                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def repository_observation_path_hints(observation: Mapping[str, object]) -> list[str]:
        hints: list[str] = []
        path_fields = ("path", "file", "filepath", "location")
        for field in path_fields:
            value = observation.get(field)
            if isinstance(value, str) and value.strip():
                hints.append(value)
        finding = observation.get("finding")
        if isinstance(finding, Mapping):
            for field in path_fields:
                value = finding.get(field)
                if isinstance(value, str) and value.strip():
                    hints.append(value)
            evidence_items = finding.get("evidence")
            if isinstance(evidence_items, (list, tuple)):
                for item in evidence_items:
                    if isinstance(item, str) and item.strip():
                        hints.append(item)
        evidence_items = observation.get("evidence")
        if isinstance(evidence_items, (list, tuple)):
            for item in evidence_items:
                if isinstance(item, str) and item.strip():
                    hints.append(item)
        return hints

    @staticmethod
    def repository_observation_match_hints(observation: Mapping[str, object]) -> list[object]:
        hints: list[object] = []
        for key in ("matches", "symbols"):
            values = observation.get(key)
            if isinstance(values, (list, tuple)):
                hints.extend(values)
            finding = observation.get("finding")
            if isinstance(finding, Mapping):
                finding_values = finding.get(key)
                if isinstance(finding_values, (list, tuple)):
                    hints.extend(finding_values)
        return hints

    def evidence_references_repository_observation(
        self, evidence: str, observations: list[dict[str, object]]
    ) -> bool:
        text = evidence.casefold()
        for observation in observations:
            if not isinstance(observation, Mapping):
                continue
            for path in self.repository_observation_path_hints(observation):
                path_text = str(path).casefold()
                if not path_text:
                    continue
                if path_text in text or Path(path_text).name in text:
                    return True
            for value in self.repository_observation_match_hints(observation):
                candidate = str(value).casefold()
                if candidate and candidate in text:
                    return True
                for symbol in re.findall(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", str(value)):
                    if symbol.casefold() in text:
                        return True
        return False

    # ------------------------------------------------------------------ #
    # Top-level quality check                                              #
    # ------------------------------------------------------------------ #

    def validate_compact_improvement_quality(
        self,
        content: str,
        entry: ExplorerBundleEntry,
        *,
        split_child: bool = False,
        observations: list[dict[str, object]] | None = None,
    ) -> None:
        if (
            entry.entry_id == "legacy"
            or entry.action == "documentation_task"
            or entry.artifact_kind == "documentation"
        ):
            return
        evidence = markdown_section(content, "Evidence")
        if self.is_generic_evidence(evidence):
            raise HarnessError("compact improvement evidence is too generic")
        problem = normalized_statement(markdown_section(content, "Problem"))
        desired = normalized_statement(markdown_section(content, "Desired Behavior"))
        if problem and desired and problem == desired:
            raise HarnessError("compact improvement desired behavior must differ from the problem")
        if not self.validate_acceptance_criteria(markdown_section(content, "Acceptance Criteria")):
            raise HarnessError("compact improvement acceptance criteria must describe observable outcomes")
        if self.requires_scope_justification(content):
            if split_child and not self.is_unfocused_bundle_child(content, entry):
                return
            raise HarnessError(
                "broad explorer improvement must split into bundle entries or include a scope justification"
            )
