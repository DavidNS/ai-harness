"""Aggregate EXPLORE base bundle and append-only deltas."""

from __future__ import annotations

from collections.abc import Mapping

from ..stores.artifact import ArtifactStore


class ExploreBundleView:
    """Build the downstream view consumed by PURPOSE/SPEC/DESIGN/TASKS."""

    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts

    def build(self) -> dict[str, object]:
        base = self._read_json("explore/outcome_bundle.json")
        deltas = [
            self._read_json(name)
            for name in sorted(self._artifacts.list())
            if name.startswith("explore/deltas/") and name.endswith(".json")
        ]
        evidence = list(base.get("evidence", [])) if isinstance(base.get("evidence"), list) else []
        for delta in deltas:
            items = delta.get("evidence", [])
            if isinstance(items, list):
                evidence.extend(items)
        view = dict(base)
        view["kind"] = "explore_bundle_view"
        view["base_kind"] = base.get("kind")
        view["evidence"] = evidence
        view["deltas"] = deltas
        return view

    def _read_json(self, name: str) -> dict[str, object]:
        value = self._artifacts.read_json(name)
        return dict(value) if isinstance(value, Mapping) else {}
