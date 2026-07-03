"""Generic JSON artifact reference validator."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from harness_v2.backend.application.bundle_artifacts import BundleValidationError


class ReferenceValidator:
    def __init__(self, allowed_ids: set[str], *, label: str = "refs") -> None:
        self._allowed_ids = allowed_ids
        self._label = label

    @staticmethod
    def ids_by_field(items: Sequence[Mapping[str, object]], field: str) -> set[str]:
        return {str(item[field]) for item in items if field in item}

    @staticmethod
    def validate_unique_field(items: Sequence[Mapping[str, object]], field: str, label: str) -> None:
        seen: set[str] = set()
        for item in items:
            value = str(item.get(field, "")).strip()
            if not value:
                continue
            if value in seen:
                raise BundleValidationError(f"{label} {field}s must be unique")
            seen.add(value)

    def validate_refs_exist(self, refs: Iterable[object]) -> None:
        missing = [ref for ref in _strings(refs) if ref not in self._allowed_ids]
        if missing:
            raise BundleValidationError(f"unknown {self._label}: " + ", ".join(missing))

    def validate_refs_in_items(self, items: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
        for item in items:
            for field in fields:
                self.validate_refs_exist(_as_list(item.get(field)))

    @staticmethod
    def validate_ordered_refs(items: Sequence[Mapping[str, object]], id_field: str, refs_field: str, label: str) -> None:
        completed: set[str] = set()
        for item in items:
            item_id = str(item.get(id_field, "")).strip()
            refs = _strings(_as_list(item.get(refs_field)))
            if any(ref not in completed for ref in refs):
                raise BundleValidationError(f"{label}s must be dependency ordered")
            if item_id:
                completed.add(item_id)


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _strings(values: Iterable[object]) -> list[str]:
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]
