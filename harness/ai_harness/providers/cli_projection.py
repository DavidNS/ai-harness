"""Pure projection helpers for subprocess-backed CLI providers."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

DEFAULT_ENV_ALLOWLIST = frozenset(
    {
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "XDG_CONFIG_HOME",
    }
)


class CapabilityProjectionError(ValueError):
    """Raised when a CLI cannot enforce the requested worker authority."""


_PERMISSION_KEYS = frozenset(
    {"paths", "commands", "skills", "mcp_tools", "timeout_seconds", "output_bytes"}
)


def provider_name(command: Sequence[str]) -> str | None:
    executable = Path(command[0]).name.lower()
    if executable in {"claude", "codex"}:
        return executable
    return None


def permission_mode(permissions: Mapping[str, object]) -> str:
    if set(permissions) != _PERMISSION_KEYS:
        raise CapabilityProjectionError("invalid worker permission projection")
    paths = permissions["paths"]
    if not isinstance(paths, list) or len(paths) != 1:
        raise CapabilityProjectionError("CLI providers require one repository-wide path rule")
    path_rule = paths[0]
    if not isinstance(path_rule, Mapping) or set(path_rule) != {"pattern", "mode"}:
        raise CapabilityProjectionError("invalid worker path permission")
    if path_rule["pattern"] != "**" or path_rule["mode"] not in {"read", "write"}:
        raise CapabilityProjectionError("CLI providers cannot enforce partial path permissions")
    for key in ("commands", "skills", "mcp_tools"):
        if not isinstance(permissions[key], list):
            raise CapabilityProjectionError(f"worker {key} permission must be a list")
    timeout = permissions["timeout_seconds"]
    if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0):
        raise CapabilityProjectionError("worker timeout_seconds must be a positive integer or null")
    output_bytes = permissions["output_bytes"]
    if not isinstance(output_bytes, int) or isinstance(output_bytes, bool) or output_bytes <= 0:
        raise CapabilityProjectionError("worker output_bytes must be a positive integer")
    return str(path_rule["mode"])


def claude_arguments(permissions: Mapping[str, object], mode: str) -> list[str]:
    if permissions["commands"]:
        raise CapabilityProjectionError("Claude cannot enforce an argv command allow-list")
    if permissions["mcp_tools"]:
        raise CapabilityProjectionError("Claude cannot enforce per-tool MCP permissions")

    # Skills are controller-resolved prompt material. Deliberately omit Claude s
    # Skill and Bash tools so it cannot discover other skills or execute commands.
    tools = "Read,Glob,Grep" if mode == "read" else "Read,Glob,Grep,Edit,Write"
    arguments = [
        "--tools", tools, "--strict-mcp-config", "--mcp-config",
        "{\"mcpServers\":{}}",
    ]
    if mode == "write":
        arguments.extend(("--permission-mode", "acceptEdits"))
    return arguments


def project_arguments(
    command: Sequence[str], permissions: Mapping[str, object]
) -> tuple[list[str], int | None, int]:
    mode = permission_mode(permissions)
    provider = provider_name(command)
    if provider == "claude":
        arguments = claude_arguments(permissions, mode)
    elif provider == "codex":
        # Current phase manifests do not grant worker-run commands or MCP tools.
        # Codex cannot project the harness permission model precisely, and nested
        # Codex sandboxes can fail before read-only workers inspect the repo.
        # Use the automation bypass for all Codex workers while failing closed for
        # permissions this adapter cannot project.
        if permissions["commands"] != []:
            raise CapabilityProjectionError("Codex cannot enforce an argv command allow-list")
        if permissions["mcp_tools"] != []:
            raise CapabilityProjectionError("Codex cannot enforce per-tool MCP permissions")
        arguments = ["--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust"]
    else:
        raise CapabilityProjectionError(
            "custom provider commands cannot enforce worker permissions"
        )
    projected = list(command)
    if provider == "codex" and projected[-2:] == ["exec", "-"]:
        projected = projected[:-1] + arguments + ["-"]
    else:
        projected += arguments
    return (
        projected,
        None if permissions["timeout_seconds"] is None else int(permissions["timeout_seconds"]),  # type: ignore[call-overload]
        int(permissions["output_bytes"]),  # type: ignore[call-overload]
    )


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def provider_model(environment: Mapping[str, str], provider: str) -> str:
    model = environment.get("AI_HARNESS_MODEL", "").strip()
    if model:
        return model
    if provider == "codex":
        return environment.get("AI_HARNESS_CODEX_MODEL", "").strip()
    if provider == "claude":
        return environment.get("AI_HARNESS_CLAUDE_MODEL", "").strip()
    return ""


def codex_config_arguments(environment: Mapping[str, str]) -> list[str]:
    arguments: list[str] = []
    model = provider_model(environment, "codex")
    if model:
        arguments.extend(("--model", model))
    effort = environment.get("AI_HARNESS_CODEX_REASONING_EFFORT", "medium").strip() or "medium"
    arguments.extend(("-c", f"model_reasoning_effort={toml_string(effort)}"))
    return arguments


def claude_config_arguments(environment: Mapping[str, str]) -> list[str]:
    model = provider_model(environment, "claude")
    return ["--model", model] if model else []


def project_environment(
    source: Mapping[str, str],
    allowed_environment: frozenset[str] = DEFAULT_ENV_ALLOWLIST,
    *,
    temp_dir: Path | None = None,
) -> dict[str, str]:
    environment = {key: source[key] for key in allowed_environment if key in source and key != "TMPDIR"}
    if temp_dir is not None:
        environment["TMPDIR"] = str(temp_dir)
    elif "TMPDIR" in source and "AI_HARNESS_INHERIT_TMPDIR" in source:
        environment["TMPDIR"] = source["TMPDIR"]
    return environment
