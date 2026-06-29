from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

from ai_harness.control_outputs import ExplorerBundleEntry
from ai_harness.errors import HarnessError
from ai_harness.orchestrator.explorer_context import ExplorerContext
from ai_harness.orchestrator.explorer_distiller import ExplorerDistiller
from ai_harness.stores.artifact import ArtifactStore

COMPACT_INPUT = """# Improvement: Slash Command Autocomplete
## Status
Proposed new improvement. Selected direction: D1.
## Problem
The interactive console needs slash-triggered command completion.
## Evidence
The request asks for `/` autocomplete.
Discovery selected D1 because it best matched the request.
Repository observation: `ai-harness` owns the console command loop.
Rejected alternatives:
- D2 was rejected because registry-only work is not enough.
Counterevidence and risks:
- Command suggestions can drift from dispatch behavior.
## Desired Behavior
Typing `/` in the TTY console opens command suggestions.
Typing more command letters narrows the suggestions.
Accepting a suggestion inserts the completed command into the input buffer.
## Implementation Notes
Inspect `ai-harness` and reuse the existing command dispatch path.
Avoid duplicate command lists that can drift from dispatch behavior.
## Acceptance Criteria
- A console-input test shows `/` renders command suggestions.
- A console-input test shows additional letters narrow suggestions.
- A console-input test shows accepting a suggestion inserts the command.
"""

DISTILLED_OUTPUT = """# Improvement: Slash Command Autocomplete
## Status
Proposed.
## Problem
The interactive console needs slash-triggered command completion.
## Evidence
The request asks for `/` autocomplete, and `ai-harness` owns the console command loop.
## Desired Behavior
Typing `/` in the TTY console opens command suggestions.
Typing more command letters narrows the suggestions.
Accepting a suggestion inserts the completed command into the input buffer.
## Implementation Notes
Inspect `ai-harness` and reuse the existing command dispatch path.
Avoid duplicate command lists that can drift from dispatch behavior.
## Acceptance Criteria
- A console-input test shows `/` renders command suggestions.
- A console-input test shows additional letters narrow suggestions.
- A console-input test shows accepting a suggestion inserts the command.
"""

INVALID_OUTPUT = """# Improvement: Slash Command Autocomplete
## Status
Proposed.
## Problem
The interactive console needs slash-triggered command completion.
## Evidence
The request asks for `/` autocomplete.
## Desired Behavior
Typing `/` in the TTY console opens command suggestions.
## Implementation Notes
Inspect `ai-harness`.
## Acceptance Criteria
- Suggestions appear.
"""


class ExplorerDistillerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.artifacts = ArtifactStore(Path(self._tmp.name), create=False)
        self.context = ExplorerContext(
            related_improvements=[{"path": "docs/explorer/improvements/existing/improvement.md"}],
            repository_observations=[{"path": "ui/console_input.py", "symbols": ["slash_command_mode"]}],
        )
        self.entry = ExplorerBundleEntry(
            entry_id="improvement-1",
            action="create",
            title="Slash Command Autocomplete",
            artifact_kind="improvement",
            content=COMPACT_INPUT,
        )

    def test_distill_uses_supplied_context(self) -> None:
        prompts: list[dict[str, object]] = []
        distiller = ExplorerDistiller(
            self.artifacts,
            request_brief_fn=lambda: "Investigate slash command autocomplete",
            stage_json_fn=lambda name: {"stage": name},
            invoke_with_repair_fn=lambda name, inputs: prompts.append(inputs) or DISTILLED_OUTPUT,
            invoke_fn=lambda name, inputs: DISTILLED_OUTPUT,
            progress_fn=lambda _: None,
        )

        result = distiller.distill(COMPACT_INPUT, self.entry, self.context, split_child=False)

        self.assertEqual(DISTILLED_OUTPUT, result.content)
        self.assertEqual(self.context.repository_observations, result.observations)
        self.assertEqual(self.context.related_improvements, prompts[0]["related_improvements"])
        self.assertEqual(self.context.repository_observations, prompts[0]["repository_observations"])

    def test_distill_retries_once_on_quality_failure(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []
        progress: list[str] = []
        distiller = ExplorerDistiller(
            self.artifacts,
            request_brief_fn=lambda: "Investigate slash command autocomplete",
            stage_json_fn=lambda name: {"stage": name},
            invoke_with_repair_fn=lambda name, inputs: calls.append((name, inputs)) or INVALID_OUTPUT,
            invoke_fn=lambda name, inputs: calls.append((name, inputs)) or DISTILLED_OUTPUT,
            progress_fn=progress.append,
        )

        result = distiller.distill(COMPACT_INPUT, self.entry, self.context, split_child=False)

        self.assertEqual(DISTILLED_OUTPUT, result.content)
        self.assertEqual(2, len(calls))
        self.assertIn("repair", calls[1][1])
        self.assertEqual(
            "Explorer distill candidate failed quality gate; invoking one repair attempt",
            progress[0],
        )

    def test_distill_raises_for_repeated_quality_failure(self) -> None:
        distiller = ExplorerDistiller(
            self.artifacts,
            request_brief_fn=lambda: "Investigate slash command autocomplete",
            stage_json_fn=lambda name: {"stage": name},
            invoke_with_repair_fn=lambda name, inputs: INVALID_OUTPUT,
            invoke_fn=lambda name, inputs: INVALID_OUTPUT,
            progress_fn=lambda _: None,
        )

        with self.assertRaises(HarnessError):
            distiller.distill(COMPACT_INPUT, self.entry, self.context, split_child=False)


if __name__ == "__main__":
    unittest.main()
