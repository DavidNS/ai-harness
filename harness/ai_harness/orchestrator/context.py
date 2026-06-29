"""RunContext — single holder of all shared orchestrator state.

Extracted from the 18 attributes that were previously scattered directly on
`self` across four mixin classes. Collaborators receive a RunContext (or a
narrow slice of it) by constructor, making dependencies explicit.

Step 3 of the refactor: introduce this seam *before* extracting collaborators
so that every future extraction has a clean injection point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from ..explorer_gate import ExplorerGateDecision
from ..canonical import CanonicalDocs
from ..config import HarnessConfig
from ..models import KnowledgeEntry
from ..providers.base import Provider
from ..router import RouteDecision
from ..stores.artifact import ArtifactStore
from ..stores.knowledge import KnowledgeStore
from ..stores.runtime import RunLock
from ..stores.state import StateStore
from ..strategy import StrategyDecision


@dataclass
class RunContext:
    """All shared state that crosses mixin / collaborator boundaries.

    Split into three tiers:
      - Identity (set once, never reassigned after __init__)
      - Stores (set in __init__, artifacts/state may be replaced in _initialize)
      - Run fields (reset or mutated each time a pipeline executes)
    """

    # --- Identity ---------------------------------------------------------
    target: Path
    config: HarnessConfig
    provider: Provider | None
    external_runtime: bool  # True when stores were injected (test isolation)

    # --- Stores -----------------------------------------------------------
    artifacts: ArtifactStore
    canonical: CanonicalDocs
    state: StateStore
    knowledge: KnowledgeStore
    lock: RunLock
    progress: Callable[[str], None]

    # --- Mutable run fields -----------------------------------------------
    route: RouteDecision | None = None
    strategy: StrategyDecision | None = None
    explorer_gate: ExplorerGateDecision | None = None
    knowledge_context: list[KnowledgeEntry] = field(default_factory=list)
    repository_observations: list[dict[str, object]] = field(default_factory=list)
    explorer_extraction_records: list[dict[str, object]] = field(default_factory=list)
    task_documents: dict[str, Mapping[str, object]] = field(default_factory=dict)
    explorer_scope_cache: dict[str, object] | None = None
    warnings: list[str] = field(default_factory=list)
