import unittest
from ai_harness.config import ConfigurationError, HarnessConfig, load_config, resource_path


class ConfigTests(unittest.TestCase):
    def test_loads_valid_cli_config(self):
        config = load_config({"AI_HARNESS_PROVIDER": "codex", "AI_HARNESS_PROVIDER_COMMAND": "codex exec", "AI_HARNESS_MODEL": "gpt-5", "AI_HARNESS_TIMEOUT": "5", "AI_HARNESS_MAX_ATTEMPTS": "2"})
        self.assertEqual(config.provider_command, ("codex", "exec"))
        self.assertEqual("gpt-5", config.model)
        self.assertEqual(2, config.max_attempts)

    def test_default_max_attempts_remains_three(self):
        self.assertEqual(3, HarnessConfig().max_attempts)
        self.assertEqual(3, load_config({}).max_attempts)
        self.assertEqual("", load_config({}).model)

    def test_model_env_precedence_is_generic_then_provider_specific(self):
        self.assertEqual("generic", load_config({"AI_HARNESS_PROVIDER": "claude", "AI_HARNESS_PROVIDER_COMMAND": "claude", "AI_HARNESS_MODEL": "generic", "AI_HARNESS_CLAUDE_MODEL": "sonnet"}).model)
        self.assertEqual("sonnet", load_config({"AI_HARNESS_PROVIDER": "claude", "AI_HARNESS_PROVIDER_COMMAND": "claude", "AI_HARNESS_CLAUDE_MODEL": "sonnet"}).model)
        self.assertEqual("gpt-5", load_config({"AI_HARNESS_PROVIDER": "codex", "AI_HARNESS_PROVIDER_COMMAND": "codex", "AI_HARNESS_CODEX_MODEL": "gpt-5"}).model)

    def test_accepts_attempts_at_controller_ceiling(self):
        self.assertEqual(10, load_config({"AI_HARNESS_MAX_ATTEMPTS": "10"}).max_attempts)

    def test_rejects_attempts_above_controller_limit(self):
        with self.assertRaisesRegex(ConfigurationError, "one and ten"):
            load_config({"AI_HARNESS_MAX_ATTEMPTS": "11"})

    def test_rejects_attempts_below_one(self):
        for value in ("0", "-1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ConfigurationError, "one and ten"):
                    load_config({"AI_HARNESS_MAX_ATTEMPTS": value})

    def test_rejects_nonnumeric_attempts(self):
        with self.assertRaisesRegex(ConfigurationError, "numeric"):
            load_config({"AI_HARNESS_MAX_ATTEMPTS": "many"})

    def test_rejects_boolean_attempts(self):
        for value in (False, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ConfigurationError, "one and ten"):
                    HarnessConfig(max_attempts=value)


    def test_git_branch_mode_defaults_current_and_accepts_create_from_main(self):
        self.assertEqual("current", load_config({}).git_branch_mode)
        self.assertEqual("create-from-main", load_config({"AI_HARNESS_GIT_BRANCH_MODE": "create-from-main"}).git_branch_mode)

    def test_github_ci_mode_defaults_baseline(self):
        self.assertEqual("baseline", load_config({}).github_ci_mode)

    def test_rejects_unknown_git_branch_mode(self):
        with self.assertRaisesRegex(ConfigurationError, "git branch mode"):
            load_config({"AI_HARNESS_GIT_BRANCH_MODE": "always"})

    def test_rejects_unknown_github_ci_mode(self):
        with self.assertRaisesRegex(ConfigurationError, "GitHub CI mode"):
            HarnessConfig(github_ci_mode="always")

    def test_resources_are_harness_relative_and_contained(self):
        self.assertEqual(resource_path("schemas").name, "schemas")
        with self.assertRaises(ConfigurationError):
            resource_path("..", "outside")
