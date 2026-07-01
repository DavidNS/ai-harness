from __future__ import annotations

import contextlib
import importlib
import sys
import io
from pathlib import Path
import tempfile
from unittest import mock
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))


def load_launcher():
    return importlib.import_module("harness.cli.console_app")


def load_ui():
    return importlib.import_module("harness.cli.ui")


def load_bootstrap():
    return importlib.import_module("harness.cli.bootstrap")


def load_model_prompts():
    return importlib.import_module("harness.cli.model_prompts")


def decision_request():
    return {
        "question": "Which path should the harness take?",
        "options": [
            {"id": "sdd_high", "label": "SDD High", "consequence": "Run high-resolution SDD."},
            {"id": "explorer", "label": "Explorer", "consequence": "Create explorer bundle."},
            {"id": "sdd_low", "label": "SDD Low", "consequence": "Use low-resolution SDD."},
        ],
        "scores": {"explorer": 8, "sdd_low": 4, "sdd_high": 10},
        "score_signals": {
            "explorer": ["explorer_language+4"],
            "sdd_low": ["strategy_sdd_low+1"],
            "sdd_high": ["strategy_sdd_high+10"],
        },
        "option_details": {
            "explorer": "Keeps the run focused on discovery before implementation.",
            "sdd_low": "Uses the smallest implementation path.",
            "sdd_high": "Runs the full SDD pipeline.",
        },
        "ranked_paths": ["explorer", "sdd_low", "sdd_high"],
        "allows_freeform": True,
    }


def ui_namespace(launcher, **overrides):
    values = {
        "cwd": Path("/repo"),
        "provider": "local",
        "verbose": False,
        "dry_run": False,
        "_interactive_ui": True,
    }
    values.update(overrides)
    return launcher.argparse.Namespace(**values)


class DecisionMenuTests(unittest.TestCase):
    def test_menu_orders_options_by_ranked_paths_and_scores(self) -> None:
        launcher = load_ui()
        ordered = launcher._ordered_options(decision_request())

        self.assertEqual(["explorer", "sdd_low", "sdd_high"], [item["id"] for item in ordered])

    def test_numeric_choice_builds_selected_option_without_inline_scores_signals(self) -> None:
        launcher = load_launcher()
        stderr = io.StringIO()
        with mock.patch("builtins.input", return_value="1"), contextlib.redirect_stderr(stderr):
            answer, selected = launcher._prompt_for_decision("run-1", decision_request())

        self.assertIsNone(answer)
        self.assertEqual("explorer", selected)
        output = stderr.getvalue()
        self.assertIn("1. Explorer [explorer] - Create explorer bundle.", output)
        self.assertNotIn("score=8", output)
        self.assertNotIn("signals=explorer_language+4", output)
        self.assertNotIn("Keeps the run focused", output)
        self.assertLess(output.index("1. Explorer"), output.index("2. SDD Low"))
        self.assertIn("Selected Explorer (explorer).", output)

    def test_decision_details_command_renders_scores_and_signals(self) -> None:
        launcher = load_launcher()
        stderr = io.StringIO()
        choices = iter(["d", "1"])
        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(choices)), contextlib.redirect_stderr(stderr):
            answer, selected = launcher._prompt_for_decision("run-1", decision_request())

        self.assertIsNone(answer)
        self.assertEqual("explorer", selected)
        output = stderr.getvalue()
        self.assertIn("Scores:", output)
        self.assertIn("- explorer: 8", output)
        self.assertIn("Option details:", output)
        self.assertIn("- explorer: Keeps the run focused on discovery before implementation.", output)
        self.assertIn("Signals:", output)
        self.assertIn("- explorer: explorer_language+4", output)

    def test_invalid_numeric_choice_reprompts_without_resuming(self) -> None:
        launcher = load_launcher()
        stderr = io.StringIO()
        choices = iter(["9", "2"])
        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(choices)), contextlib.redirect_stderr(stderr):
            answer, selected = launcher._prompt_for_decision("run-1", decision_request())

        self.assertIsNone(answer)
        self.assertEqual("sdd_low", selected)
        self.assertIn("Enter a menu number.", stderr.getvalue())

    def test_freeform_decision_builds_answer_when_allowed(self) -> None:
        launcher = load_launcher()
        stderr = io.StringIO()
        choices = iter(["f", "Use a custom answer."])
        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(choices)), contextlib.redirect_stderr(stderr):
            answer, selected = launcher._prompt_for_decision("run-1", decision_request())

        self.assertEqual("Use a custom answer.", answer)
        self.assertIsNone(selected)
        self.assertIn("Selected free-form answer.", stderr.getvalue())


    def test_slash_looking_request_input_is_preserved_literally(self) -> None:
        launcher = load_launcher()
        choices = iter(["/help", "Fix tests", "."])

        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(choices)), contextlib.redirect_stderr(io.StringIO()):
            request = launcher._interactive_request()

        self.assertEqual("/help\nFix tests", request)

    def test_decision_slash_help_is_invalid_menu_input(self) -> None:
        launcher = load_launcher()
        stderr = io.StringIO()
        choices = iter(["/help", "1"])

        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(choices)), contextlib.redirect_stderr(stderr):
            answer, selected = launcher._prompt_for_decision("run-1", decision_request())

        self.assertIsNone(answer)
        self.assertEqual("explorer", selected)
        self.assertIn("Enter a menu number.", stderr.getvalue())


    def test_model_prompt_prefers_configured_model_over_provider_default(self) -> None:
        launcher = load_model_prompts()
        with mock.patch.object(launcher, "_interactive_stdin", return_value=False), \
            mock.patch.dict(launcher.os.environ, {"AI_HARNESS_MODEL": "gpt-5"}, clear=False):
            self.assertEqual("gpt-5", launcher._prompt_for_model("codex"))

    def test_model_prompt_accepts_explicit_override_without_prompting(self) -> None:
        launcher = load_model_prompts()
        self.assertEqual("custom-model", launcher._prompt_for_model("codex", explicit="custom-model"))

    def test_model_prompt_uses_claude_specific_config_noninteractive(self) -> None:
        launcher = load_model_prompts()
        with mock.patch.object(launcher, "_interactive_stdin", return_value=False), \
            mock.patch.dict(launcher.os.environ, {"AI_HARNESS_CLAUDE_MODEL": "sonnet"}, clear=True):
            self.assertEqual("sonnet", launcher._prompt_for_model("claude"))

    def test_model_prompt_lists_provider_choices_and_custom_entry(self) -> None:
        launcher = load_model_prompts()
        selected_items = []

        def choose(_title_lines, items, **_kwargs):
            selected_items.extend(items)
            return items[1]

        with mock.patch.object(launcher, "_interactive_stdin", return_value=True), \
            mock.patch.object(launcher, "model_choices", return_value=[launcher.ModelChoice("GPT-5", "gpt-5")]), \
            mock.patch.object(launcher, "_menu_prompt", side_effect=choose), \
            mock.patch.dict(launcher.os.environ, {}, clear=True):
            selected = launcher._prompt_for_model("codex")

        self.assertEqual("gpt-5", selected)
        self.assertEqual("Use provider default", selected_items[0].label)
        self.assertEqual("GPT-5", selected_items[1].label)
        self.assertEqual("Enter custom model", selected_items[-1].label)

    def test_model_prompt_dedupes_configured_choice(self) -> None:
        launcher = load_model_prompts()
        selected_items = []

        def choose(_title_lines, items, **_kwargs):
            selected_items.extend(items)
            return items[0]

        with mock.patch.object(launcher, "_interactive_stdin", return_value=True), \
            mock.patch.object(launcher, "model_choices", return_value=[launcher.ModelChoice("GPT-5", "gpt-5")]), \
            mock.patch.object(launcher, "_menu_prompt", side_effect=choose), \
            mock.patch.dict(launcher.os.environ, {"AI_HARNESS_MODEL": "gpt-5"}, clear=True):
            selected = launcher._prompt_for_model("codex")

        self.assertEqual("gpt-5", selected)
        self.assertEqual(["Use configured model [gpt-5]", "Use provider default", "Enter custom model"], [item.label for item in selected_items])

    def test_reasoning_effort_prompt_is_codex_only(self) -> None:
        launcher = load_model_prompts()
        with mock.patch.object(launcher, "_interactive_stdin", return_value=False), \
            mock.patch.dict(launcher.os.environ, {"AI_HARNESS_CODEX_REASONING_EFFORT": "high"}, clear=True):
            self.assertEqual("high", launcher._prompt_for_reasoning_effort("codex"))
            self.assertIsNone(launcher._prompt_for_reasoning_effort("claude"))

    def test_reasoning_effort_prompt_lists_efforts(self) -> None:
        launcher = load_model_prompts()
        selected_items = []

        def choose(_title_lines, items, **_kwargs):
            selected_items.extend(items)
            return next(item for item in items if item.value == "xhigh")

        with mock.patch.object(launcher, "_interactive_stdin", return_value=True), \
            mock.patch.object(launcher, "_menu_prompt", side_effect=choose), \
            mock.patch.dict(launcher.os.environ, {}, clear=True):
            selected = launcher._prompt_for_reasoning_effort("codex")

        self.assertEqual("xhigh", selected)
        self.assertEqual("Use provider default", selected_items[0].label)
        self.assertIn("Medium", [item.label for item in selected_items])
        self.assertIn("Extra high", [item.label for item in selected_items])

    def test_decision_slash_exit_is_invalid_menu_input(self) -> None:
        launcher = load_launcher()
        stderr = io.StringIO()
        choices = iter(["/exit", "1"])

        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(choices)), contextlib.redirect_stderr(stderr):
            answer, selected = launcher._prompt_for_decision("run-1", decision_request())

        self.assertIsNone(answer)
        self.assertEqual("explorer", selected)
        self.assertIn("Enter a menu number.", stderr.getvalue())

    def test_menu_prompt_tty_arrow_down_enter_selects_highlighted_item(self) -> None:
        launcher = load_ui()

        class DummyRawTerminal:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        keys = iter(["down", "\n"])
        with mock.patch.object(launcher, "_interactive_stdin", return_value=True), \
            mock.patch.object(launcher, "_RawTerminal", DummyRawTerminal), \
            mock.patch.object(launcher, "_read_key", side_effect=lambda: next(keys)), \
            contextlib.redirect_stderr(io.StringIO()):
            selected = launcher._menu_prompt(
                ["Title"],
                [launcher._MenuItem("1", "One", "one"), launcher._MenuItem("2", "Two", "two")],
                help_kind="action",
            )

        self.assertEqual("two", selected.value)

    def test_text_prompt_tty_alt_enter_inserts_newline(self) -> None:
        launcher = load_ui()

        class DummyRawTerminal:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        keys = iter(["H", "alt-enter", "i", "\n"])
        with mock.patch.object(launcher, "_interactive_stdin", return_value=True), \
            mock.patch.object(launcher, "_RawTerminal", DummyRawTerminal), \
            mock.patch.object(launcher, "_read_key", side_effect=lambda: next(keys)), \
            contextlib.redirect_stderr(io.StringIO()):
            value = launcher._text_prompt("Request: ", help_kind="request")

        self.assertEqual("H\ni", value)

    def test_interactive_request_preserves_slash_lines(self) -> None:
        launcher = load_launcher()
        choices = iter(["First line", "/help", "Second line", "."])

        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(choices)), contextlib.redirect_stderr(io.StringIO()):
            request = launcher._interactive_request()

        self.assertEqual("First line\n/help\nSecond line", request)




    def test_console_model_command_stores_selected_model(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher, provider="codex")
        stderr = io.StringIO()

        with mock.patch.object(launcher, "_prompt_for_model", return_value="gpt-5"), \
            mock.patch.object(launcher, "_prompt_for_reasoning_effort", return_value="high"), \
            contextlib.redirect_stderr(stderr):
            code = launcher._console_command(namespace, "model")

        self.assertEqual(0, code)
        self.assertEqual("gpt-5", namespace.model)
        self.assertEqual("high", namespace.reasoning_effort)
        self.assertIn("Selected model: gpt-5", stderr.getvalue())
        self.assertIn("Selected reasoning effort: high", stderr.getvalue())

    def test_console_slash_model_is_literal_request(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher, provider="codex")

        with mock.patch.object(launcher, "_unfinished_runs", return_value=[]), \
            mock.patch.object(launcher, "_start_job", return_value=0) as start_job:
            code = launcher._console_command(namespace, "/model")

        self.assertEqual(0, code)
        start_job.assert_called_once()
        self.assertEqual("/model", start_job.call_args.kwargs["request_override"])

    def test_start_request_prompt_preserves_slash_lines(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher, provider="codex")
        choices = iter(["/model", "Fix tests", "."])

        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(choices)), contextlib.redirect_stderr(io.StringIO()):
            request = launcher._interactive_start_request(namespace)

        self.assertEqual("/model\nFix tests", request)
        self.assertIsNone(namespace.model)

    def test_console_ci_mode_command_stores_selected_mode(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            code = launcher._console_command(namespace, "ci-mode branch")

        self.assertEqual(0, code)
        self.assertEqual("branch", namespace.github_ci_mode)
        self.assertIn("Selected GitHub CI mode: branch", stderr.getvalue())

    def test_console_status_dispatches_action(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)
        with mock.patch.object(launcher, "_run", return_value=0) as run:
            code = launcher._console_command(namespace, "status")

        self.assertEqual(0, code)
        self.assertEqual(["--cwd", "/repo", "--status"], run.call_args.args[0])

    def test_console_menu_uses_action_registry(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)
        selected_items = []

        def choose(_title_lines, items, **_kwargs):
            selected_items.extend(items)
            return next(item for item in items if item.value == "runs")

        with mock.patch.object(launcher, "_menu_prompt", side_effect=choose), \
            mock.patch.object(launcher, "_run", return_value=0) as run:
            code = launcher._console_command(namespace, "")

        self.assertEqual(0, code)
        self.assertIn("status", [item.value for item in selected_items])
        self.assertIn("model", [item.value for item in selected_items])
        self.assertIn("exit", [item.value for item in selected_items])
        self.assertEqual(["--cwd", "/repo", "--show-runs"], run.call_args.args[0])


    def test_console_install_packages_delegates_explicit_optional_groups(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)

        with mock.patch.object(launcher, "_run", return_value=0) as run:
            code = launcher._console_command(namespace, "install-packages security github --dry-install")

        self.assertEqual(0, code)
        self.assertEqual(
            ["--cwd", "/repo", "--install-packages", "--package", "security", "--package", "github", "--dry-install"],
            run.call_args.args[0],
        )

    def test_console_install_packages_prompts_for_optionals_when_interactive(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)

        def choose(_title_lines, items, **_kwargs):
            return [item for item in items if item.value in {"security", "github"}]

        with mock.patch.object(launcher.sys.stdin, "isatty", return_value=True), \
            mock.patch.object(launcher, "_multi_select_prompt", side_effect=choose) as prompt, \
            mock.patch.object(launcher, "_run", return_value=0) as run:
            code = launcher._console_command(namespace, "install-packages")

        self.assertEqual(0, code)
        prompt.assert_called_once()
        self.assertEqual(
            ["--cwd", "/repo", "--install-packages", "--package", "security", "--package", "github"],
            run.call_args.args[0],
        )

    def test_console_unknown_slash_text_starts_literal_request(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)

        with mock.patch.object(launcher, "_unfinished_runs", return_value=[]), \
            mock.patch.object(launcher, "_start_job", return_value=0) as start_job:
            code = launcher._console_command(namespace, "/wat")

        self.assertEqual(0, code)
        start_job.assert_called_once()
        self.assertEqual("/wat", start_job.call_args.kwargs["request_override"])

    def test_console_loop_exits_on_exit_command(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)
        choices = iter(["exit"])
        stderr = io.StringIO()

        with mock.patch.object(launcher, "_startup_recovery", return_value=None), \
            mock.patch("harness.cli.console_controller.interactive_console_line", side_effect=lambda _deps, _prompt="aihui> ": next(choices)), \
            contextlib.redirect_stderr(stderr):
            code = launcher._console_loop(namespace)

        self.assertEqual(0, code)
        self.assertIn("AI Code Harness console", stderr.getvalue())


    def test_start_forwards_selected_reasoning_effort(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher, provider="codex", prompt_file=None, model="gpt-5.5", reasoning_effort="xhigh")
        with mock.patch.object(launcher.sys.stdin, "isatty", return_value=False), \
            mock.patch.object(launcher, "_run_and_follow_decisions", return_value=0) as run:
            code = launcher._start(namespace, ["Fix tests"])

        self.assertEqual(0, code)
        backend = run.call_args.args[1]
        self.assertIn("--model", backend)
        self.assertIn("gpt-5.5", backend)
        self.assertIn("--reasoning-effort", backend)
        self.assertIn("xhigh", backend)

    def test_start_forwards_selected_github_ci_mode(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher, prompt_file=None, github_ci_mode="branch")
        with mock.patch.object(launcher.sys.stdin, "isatty", return_value=False), \
            mock.patch.object(launcher, "_run_and_follow_decisions", return_value=0) as run:
            code = launcher._start(namespace, ["Fix tests"])

        self.assertEqual(0, code)
        backend = run.call_args.args[1]
        self.assertIn("--github-ci-mode", backend)
        self.assertIn("branch", backend)

    def test_run_and_follow_decisions_resumes_single_waiting_run(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)
        current = Path("/tmp/current-run")
        state = {"run_id": "run-1", "status": "waiting_for_user", "current_phase": "DESIGN"}
        waiting = [(current, state)]

        with mock.patch.object(launcher, "_run", side_effect=[0, 0]) as run, \
            mock.patch.object(launcher.sys.stdin, "isatty", return_value=True), \
            mock.patch.object(launcher, "_unfinished_runs", side_effect=[[], waiting, []]), \
            mock.patch.object(launcher, "_find_run", return_value=waiting[0]), \
            mock.patch.object(launcher, "_decision_request", return_value={"question": "Q?", "options": [], "allows_freeform": True}), \
            mock.patch.object(launcher, "_prompt_for_decision", return_value=(None, "preserve")):
            code = launcher._run_and_follow_decisions(namespace, ["--cwd", "/repo", "--provider", "local"], request="start")

        self.assertEqual(0, code)
        self.assertEqual(2, run.call_count)
        resumed_args = run.call_args_list[1].args[0]
        self.assertIn("--resume", resumed_args)
        self.assertIn("run-1", resumed_args)
        self.assertIn("--selected-option", resumed_args)
        self.assertIn("preserve", resumed_args)

    def test_resume_forwards_selected_github_ci_mode(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher, github_ci_mode="branch")
        current = Path("/tmp/current-run")
        state = {"run_id": "run-1", "status": "active", "current_phase": "IMPLEMENT"}

        with mock.patch.object(launcher, "_find_run", return_value=(current, state)), \
            mock.patch.object(launcher, "_run", return_value=0) as run:
            code = launcher._resume(namespace, "run-1", follow_decisions=False)

        self.assertEqual(0, code)
        backend = run.call_args.args[0]
        self.assertIn("--github-ci-mode", backend)
        self.assertIn("branch", backend)

    def test_discovers_improvement_candidates_with_titles(self) -> None:
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            first = repository / "docs/explorer/improvements/alpha/improvement.md"
            second = repository / "docs/explorer/improvements/group/beta/improvement.md"
            for path, title in ((first, "Alpha"), (second, "Beta")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# Improvement: {title}\n## Status\nProposed\n", encoding="utf-8")

            candidates = launcher._discover_improvement_candidates(repository)

        self.assertEqual([
            "docs/explorer/improvements/alpha/improvement.md",
            "docs/explorer/improvements/group/beta/improvement.md",
        ], [candidate.path for candidate in candidates])
        self.assertEqual(["Alpha", "Beta"], [candidate.title for candidate in candidates])

    def test_validate_explorer_scope_rejects_broad_docs_and_accepts_artifacts_and_folders(self) -> None:
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs/explorer/improvements/alpha/improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement: Alpha\n", encoding="utf-8")

            broad = launcher._validate_explorer_scope(repository, "docs/")
            file_scope = launcher._validate_explorer_scope(repository, "docs/explorer/improvements/alpha/improvement.md")
            folder_scope = launcher._validate_explorer_scope(repository, "docs/explorer/improvements/alpha")

        self.assertFalse(broad[0])
        self.assertIn("docs/explorer/improvements", broad[2])
        self.assertEqual((True, "docs/explorer/improvements/alpha/improvement.md", ""), file_scope)
        self.assertEqual((True, "docs/explorer/improvements/alpha", ""), folder_scope)


    def test_prepare_console_request_does_not_prompt_for_plain_docs_edit(self) -> None:
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            namespace = launcher.argparse.Namespace(cwd=repository)

            with mock.patch("sys.stdin.isatty", return_value=True),                 mock.patch("builtins.input") as prompt,                 contextlib.redirect_stderr(io.StringIO()):
                request = launcher._prepare_console_request(namespace, "Fix docs/README.md typo")

        self.assertEqual("Fix docs/README.md typo", request)
        prompt.assert_not_called()

    def test_prepare_console_request_appends_selected_scope_for_full_implementation(self) -> None:
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs/explorer/improvements/alpha/improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement: Alpha\n", encoding="utf-8")
            namespace = launcher.argparse.Namespace(cwd=repository)

            with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="1"), \
                contextlib.redirect_stderr(io.StringIO()):
                request = launcher._prepare_console_request(namespace, "Full implementation for launcher recovery")

        self.assertEqual(
            "Full implementation for launcher recovery docs/explorer/improvements/alpha/improvement.md",
            request,
        )


    def test_prepare_console_request_prompts_for_hyphenated_full_sdd(self) -> None:
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            artifact = repository / "docs/explorer/improvements/alpha/improvement.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("# Improvement: Alpha\n", encoding="utf-8")
            namespace = launcher.argparse.Namespace(cwd=repository)

            with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="1"), \
                contextlib.redirect_stderr(io.StringIO()):
                request = launcher._prepare_console_request(namespace, "full-SDD for launcher recovery")

        self.assertEqual(
            "full-SDD for launcher recovery docs/explorer/improvements/alpha/improvement.md",
            request,
        )

    def test_run_and_follow_decisions_ignores_preexisting_waiting_run(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)
        stale = (Path("/tmp/current-stale"), {"run_id": "stale", "status": "waiting_for_user"})

        with mock.patch.object(launcher, "_run", return_value=0) as run, \
            mock.patch.object(launcher.sys.stdin, "isatty", return_value=True), \
            mock.patch.object(launcher, "_unfinished_runs", side_effect=[[stale], [stale]]), \
            mock.patch.object(launcher, "_prompt_for_decision") as prompt:
            code = launcher._run_and_follow_decisions(namespace, ["--cwd", "/repo", "--provider", "local"], request="start")

        self.assertEqual(0, code)
        self.assertEqual(1, run.call_count)
        prompt.assert_not_called()

    def test_continue_completed_run_starts_next_bundle_from_snapshot(self) -> None:
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            snapshot = repository / ".ai-harness" / "artifacts" / "runs" / "run-1"
            (snapshot / "published").mkdir(parents=True)
            (snapshot / "state.json").write_text(
                '{"run_id":"run-1","status":"completed","user_input":"Original prompt","current_phase":"COMPLETED"}\n',
                encoding="utf-8",
            )
            (snapshot / "run-title.json").write_text('{"title":"Explore launcher recovery"}\n', encoding="utf-8")
            (snapshot / "published" / "explore-handoff.json").write_text('{"schema_version":1}\n', encoding="utf-8")
            namespace = ui_namespace(launcher, cwd=repository, prompt_file=None)

            def choose(_title_lines, items, **_kwargs):
                return items[0]

            with mock.patch.object(launcher, "_unfinished_runs", return_value=[]), \
                mock.patch.object(launcher, "_menu_prompt", side_effect=choose), \
                mock.patch.object(launcher, "_start", return_value=0) as start:
                code = launcher._continue_completed_run(namespace)

        self.assertEqual(0, code)
        _, _, kwargs = start.mock_calls[0]
        self.assertEqual("proposal", kwargs["flow"])
        self.assertEqual("run-1", kwargs["source_run"])
        self.assertIn("Explore launcher recovery", kwargs["request_override"])


    def test_console_help_is_rendered_from_action_registry(self) -> None:
        launcher = load_launcher()
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            launcher._console_help()

        output = stderr.getvalue()
        self.assertIn("status: Show status", output)
        self.assertIn("ci-mode: Select GitHub CI mode", output)
        self.assertIn("tdd: Run TDD bundle", output)
        self.assertNotIn("/status", output)

    def test_console_mvu_update_separates_commands_menu_and_requests(self) -> None:
        from harness.cli.console.model import ConsoleActionSpec, ConsoleModel
        from harness.cli.console.messages import SubmitLine
        from harness.cli.console.update import update

        model = ConsoleModel(actions=(ConsoleActionSpec("status", "Show status", "s"),))
        _, command_effects = update(model, SubmitLine("status"))
        menu_model, menu_effects = update(model, SubmitLine(""))
        _, request_effects = update(model, SubmitLine("/status"))

        self.assertEqual("dispatch_action", command_effects[0].kind)
        self.assertEqual("status", command_effects[0].value)
        self.assertEqual("menu", menu_model.screen)
        self.assertEqual("open_menu", menu_effects[0].kind)
        self.assertEqual("start_request", request_effects[0].kind)
        self.assertEqual("/status", request_effects[0].value)

    def test_console_action_registry_has_handlers_for_every_action(self) -> None:
        from harness.cli.console_actions import CONSOLE_ACTIONS
        from harness.cli.console_controller import handled_console_action_names

        self.assertEqual({action.name for action in CONSOLE_ACTIONS}, handled_console_action_names())

    def test_dispatch_unknown_console_action_does_not_start_request(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            code = launcher._dispatch_console_action(namespace, "unknown-action", [], "unknown-action")

        self.assertEqual(2, code)
        self.assertIn("unknown console action", stderr.getvalue())

    def test_console_prompt_preserves_slash_text(self) -> None:
        launcher = load_launcher()

        class DummyRawTerminal:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        keys = iter(["/", "s", "t", "\n"])
        with mock.patch.object(launcher, "_interactive_stdin", return_value=True), \
            mock.patch.object(launcher, "_RawTerminal", DummyRawTerminal), \
            mock.patch.object(launcher, "_read_key", side_effect=lambda: next(keys)), \
            contextlib.redirect_stderr(io.StringIO()):
            line = launcher._interactive_console_line()

        self.assertEqual("/st", line)

    def test_console_prompt_blank_line_opens_menu_contract(self) -> None:
        launcher = load_launcher()

        class DummyRawTerminal:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        keys = iter(["\n"])
        with mock.patch.object(launcher, "_interactive_stdin", return_value=True), \
            mock.patch.object(launcher, "_RawTerminal", DummyRawTerminal), \
            mock.patch.object(launcher, "_read_key", side_effect=lambda: next(keys)), \
            contextlib.redirect_stderr(io.StringIO()):
            line = launcher._interactive_console_line()

        self.assertEqual("", line)

    def test_console_prompt_menu_literal_opens_menu_contract(self) -> None:
        launcher = load_launcher()

        class DummyRawTerminal:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        keys = iter(["/", "m", "e", "n", "u", "\n"])
        with mock.patch.object(launcher, "_interactive_stdin", return_value=True), \
            mock.patch.object(launcher, "_RawTerminal", DummyRawTerminal), \
            mock.patch.object(launcher, "_read_key", side_effect=lambda: next(keys)), \
            contextlib.redirect_stderr(io.StringIO()):
            line = launcher._interactive_console_line()

        self.assertEqual("/menu", line)

    def test_console_prompt_render_redraws_single_prompt_row(self) -> None:
        launcher = load_launcher()
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            previous = launcher._render_console_prompt(["F"], 0)
            current = launcher._render_console_prompt(["F", "i", "x"], previous)

        output = stderr.getvalue()
        self.assertEqual(1, previous)
        self.assertEqual(1, current)
        self.assertIn("aihui> Fix", output)
        self.assertIn(f"\x1b[{previous}F", output)

    def test_bootstrap_actions_are_derived_from_top_level_registry(self) -> None:
        bootstrap = load_bootstrap()

        self.assertIn("status", bootstrap.ACTIONS)
        self.assertIn("artifacts", bootstrap.ACTIONS)
        self.assertIn("raw", bootstrap.ACTIONS)
        self.assertIn("tdd", bootstrap.ACTIONS)
        self.assertNotIn("start", bootstrap.ACTIONS)
        self.assertNotIn("model", bootstrap.ACTIONS)

    def test_console_plain_request_starts_background_job(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)

        with mock.patch.object(launcher, "_unfinished_runs", return_value=[]), \
            mock.patch.object(launcher, "_start_job", return_value=0) as start_job:
            code = launcher._console_command(namespace, "Fix tests")

        self.assertEqual(0, code)
        start_job.assert_called_once()
        self.assertEqual("Fix tests", start_job.call_args.kwargs["request_override"])

    def test_console_blocks_plain_request_when_unfinished_runs_require_selection(self) -> None:
        launcher = load_launcher()
        namespace = ui_namespace(launcher)
        stderr = io.StringIO()
        unfinished = [(Path("/tmp/current-run"), {"run_id": "run-1", "status": "active"})]

        with mock.patch.object(launcher, "_unfinished_runs", return_value=unfinished), \
            mock.patch.object(launcher, "_start") as start, \
            contextlib.redirect_stderr(stderr):
            code = launcher._console_command(namespace, "Fix tests")

        self.assertEqual(1, code)
        start.assert_not_called()
        self.assertIn("resolve unfinished runs", stderr.getvalue())

if __name__ == "__main__":
    unittest.main()
