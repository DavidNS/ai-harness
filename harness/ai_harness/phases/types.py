"""Phase definition types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from ..capabilities import CapabilityManifest, load_manifest
from .errors import PhaseValidationError

Validator = Callable[[str], object]


@dataclass(frozen=True, slots=True)
class PhaseDefinition:
    name: str
    artifact: str
    required_inputs: tuple[str, ...]
    sections: tuple[str, ...]
    validator: Validator
    heading: str | None = None

    @property
    def playbook(self) -> str:
        return f"{self.name}.md"

    @property
    def prompt(self) -> str:
        return f"{self.name}.md"

    @property
    def capability_manifest(self) -> str:
        return f"{self.name}.json"

    def build_input(self, supplied: Mapping[str, object]) -> dict[str, object]:
        missing = set(self.required_inputs) - set(supplied)
        extra = set(supplied) - set(self.required_inputs)
        if missing or extra:
            raise PhaseValidationError(
                f"invalid {self.name} inputs: missing={sorted(missing)}, extra={sorted(extra)}"
            )
        return {name: supplied[name] for name in self.required_inputs}

    def validate(self, candidate: str) -> object:
        return self.validator(candidate)

    def load_manifest(self, harness_root: Path) -> CapabilityManifest:
        manifest = load_manifest(harness_root / "capabilities" / self.capability_manifest)
        if manifest.phase != self.name:
            raise PhaseValidationError("capability manifest phase mismatch")
        return manifest
