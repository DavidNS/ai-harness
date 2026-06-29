  We need to isolate the harness from users local configurations:
  
  For your current architecture, I’d split this into two layers:

  1. Stop installing bootstrap files
     The old install behavior writes:
      - global Codex: ~/.codex/AGENTS.md
      - project Codex: <project>/AGENTS.md
      - global Claude: ~/.claude/CLAUDE.md
      - project Claude: <project>/CLAUDE.md

     Since your entrypoint is now direct Python, that part is obsolete. You can remove it with:

     python3 scripts/uninstall.py --codex --claude --global
     python3 scripts/uninstall.py --codex --claude --project /path/to/project

  2. Isolate provider subprocesses
     The harness currently launches real provider CLIs, so their own discovery can still affect workers.

     For Claude, this is straightforward: your installed CLI has --safe-mode, which disables CLAUDE.md, skills, plugins, hooks, MCP config, etc. It also has --bare, but --safe-mode is probably
     the better default because it preserves normal auth.

     For Codex, your installed CLI exposes:

     --ignore-user-config
     --ignore-rules
     --ephemeral

     Those avoid $CODEX_HOME/config.toml, exec policy rules, and session persistence. But I did not see a direct --ignore-agents flag in codex exec --help, so a project-level AGENTS.md can
     still be a risk if Codex is run with the repo as its working root.

  The clean harness-side fix would be:

  - Stop generating AGENTS.md / CLAUDE.md from scripts/install.py.
  - Add provider isolation flags:
      - Codex: --ignore-user-config --ignore-rules --ephemeral
      - Claude: --safe-mode --no-session-persistence

  - For full Codex AGENTS.md isolation, either ensure no AGENTS.md exists in the target repo, or change worker execution so Codex runs from a clean temp root and receives the repo via --add-
    dir. That second option is more invasive because prompts/workers may assume the repo is the cwd.

  So: yes for .claude and most .codex config interference; partially for Codex AGENTS.md unless you remove it or change the worker cwd model.
