# Obsidian Memory — a Claude Code plugin

Gives every project persistent memory in an Obsidian vault: `<project>/.obsidian-vault/`. It holds the context `CLAUDE.md`, session history, specs, plans, processes, decisions (ADRs), bugs and retrospectives. The vault is versioned in the project's own git repository.

- **Fewer tokens:** to resume, Claude loads only `CLAUDE.md` and the last session summary (a few KB) instead of rebuilding context.
- **Memory outside the context window:** the vault grows on disk, and Claude reads what it needs when it needs it.
- **Automatic:** hooks archive every session and commit the vault (only the vault, never pushed, with a secret scan).

> Notes are written in your conversation language; dates use the `dd-mm-yyyy` format.

## Requirements

| | macOS | Linux | Windows |
|---|---|---|---|
| Claude Code | ✔ | ✔ | ✔ |
| Python 3.8+ | `python3` | `python3` | `python` or `py -3` |
| git | ✔ | ✔ | **Git for Windows** (provides Git Bash, used by the hooks) |
| Obsidian Desktop | optional | optional | optional |

Run `/obsidian-memory:vault doctor` to check. Anything missing can be installed by the plugin itself (`winget`, `brew` or `flatpak`), **always with your approval**. If Obsidian isn't found, its download page (https://obsidian.md/download) opens.

## Installation

**From GitHub (recommended):** inside Claude Code, run:
```
/plugin marketplace add marcuswmc/obsidian-memory-plugin
/plugin install obsidian-memory@obsidian-memory
```

**Manual:** clone or copy this repository to `~/.claude/skills/obsidian-memory/` (on Windows, `%USERPROFILE%\.claude\skills\obsidian-memory\`). Because the folder contains `.claude-plugin/plugin.json`, Claude Code loads it as a plugin (`obsidian-memory@skills-dir`) in the next session.

Use **only one** of the two methods: with both installed, the hooks run twice. Then restart Claude Code (or run `/reload-plugins`) and check with `/obsidian-memory:vault doctor`.

The hooks ship with the plugin (`hooks/hooks.json`), so there's no need to edit `settings.json`.

### Claude Cowork
The same plugin works in Cowork (Claude desktop app). Add the marketplace `marcuswmc/obsidian-memory-plugin` in Cowork's plugin settings and install **Obsidian Memory**. Then **select the project folder** when you start a session: Cowork works in its own session folder, so the plugin uses the selected folder as the project and keeps the vault there. Without a selected folder, memory stays off and nothing is written inside Cowork's session folders.

### Windows
- Install [Git for Windows](https://git-scm.com/downloads/win). The hooks run `bash scripts/vault …`, and Git Bash is what provides `bash`. If Claude Code can't find Git Bash, set `CLAUDE_CODE_GIT_BASH_PATH` (for example `C:\Program Files\Git\bin\bash.exe`) in the `env` block of `settings.json`.
- The `scripts/vault` launcher tries `python3`, `python` and `py -3`, in that order, and skips the Microsoft Store shortcut that isn't a real Python.
- Everything is read and written as UTF-8.
- Obsidian is looked up in `%LOCALAPPDATA%\Programs\Obsidian`, and its configuration in `%APPDATA%\obsidian\obsidian.json`.

## Usage

| Command | What it does |
|---|---|
| `/obsidian-memory:vault init` | Creates the vault, runs `git init` if needed, commits and opens it in Obsidian |
| `/obsidian-memory:vault save` | Writes the session summary, updates Current State and commits the vault |
| `/obsidian-memory:vault status` | Shows the state of the vault, git, Obsidian, and any alerts |
| `/obsidian-memory:vault open` | Registers the vault in Obsidian and opens it (asks before restarting the app) |
| `/obsidian-memory:vault doctor` | Checks requirements and offers to install anything missing |

It also works with plain-language requests: "save the session", "record this decision", "where did we leave off?".

## Hooks

| Event | Action |
|---|---|
| SessionStart | Injects the last session and any alerts; after a compaction, also re-injects `CLAUDE.md` |
| PreCompact | Archives the transcript and commits the vault before compaction |
| SessionEnd | Archives the transcript and memory, and commits the vault |

## Guarantees

- Commits include **only** `.obsidian-vault/`. Whatever you have staged is left untouched, and nothing is ever pushed.
- Transcripts and memory snapshots stay out of git (`.obsidian-vault/.gitignore`).
- Before each commit, the script scans for secrets. If it finds any, it doesn't commit and shows an alert at the start of the next session.
- No vault is ever created automatically in your home folder, Downloads, Desktop, Documents, temp folders or a drive root.
- Nothing is installed and Obsidian is never restarted without your approval.

## Configuration (`scripts/vault.py`)

| Constant | Default |
|---|---|
| `VAULT_DIR` | `.obsidian-vault` |
| `CONTEXT_LIMIT` | 12,000 characters injected |
| `SECRET_PATTERNS` | secret patterns checked before each commit |
| `OBSIDIAN_CONFIG` | initial `.obsidian/` settings (Daily Notes, Templates) |
| `excluded()` | folders where a vault is never created |

## License

MIT
