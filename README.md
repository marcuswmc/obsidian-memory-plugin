# Obsidian Memory — a Claude Code plugin

Gives every project persistent memory in an Obsidian vault: `<project>/obsidian-vault/`. It holds the context `CLAUDE.md`, session history, specs, plans, processes, decisions (ADRs), bugs and retrospectives, all as plain Markdown next to your code.

- **Resume without explaining:** when a session starts in a project with a vault, Claude already has the project context and the last session summary. No file reads or tool calls needed.
- **Fewer tokens:** Claude loads only `CLAUDE.md` and the last session (a few KB) instead of rebuilding context. Everything else stays on disk until a task needs it.
- **Automatic:** hooks archive every session into the vault.
- **Git and Obsidian are optional:** version the vault with git and browse it in Obsidian, or use neither. The vault works as plain Markdown.

> Notes are written in your conversation language; dates use the `dd-mm-yyyy` format.

🌐 **Website:** [obsidian-memory-site.vercel.app](https://obsidian-memory-site.vercel.app)

📊 **Presentation (PDF, Portuguese):** [features, usage and token-savings benchmark](docs/apresentacao/obsidian-memory.pdf)

## Requirements

| | macOS | Linux | Windows |
|---|---|---|---|
| Claude Code | required | required | required |
| Python 3.8+ | required (`python3`) | required (`python3`) | required (`python` or `py -3`) |
| git | optional | optional | **Git for Windows required** (its Git Bash runs the hooks), even if you don't version the vault |
| Obsidian Desktop | optional | optional | optional |

Run `/obsidian-memory:vault doctor` to check. When you choose git or Obsidian and it's missing, the plugin installs it with your system's package manager (Homebrew, winget, apt/dnf or flatpak), **always with your approval**. Without a package manager, it opens the official installer or download page instead; it never installs a package manager.

## Installation

**From GitHub (recommended):** inside Claude Code, run:
```
/plugin marketplace add marcuswmc/obsidian-memory-plugin
/plugin install obsidian-memory@obsidian-memory
```

**Manual:** clone or copy this repository to `~/.claude/skills/obsidian-memory/` (on Windows, `%USERPROFILE%\.claude\skills\obsidian-memory\`). Because the folder contains `.claude-plugin/plugin.json`, Claude Code loads it as a plugin (`obsidian-memory@skills-dir`) in the next session.

Use **only one** of the two methods: with both installed, the hooks run twice. Then restart Claude Code (or run `/reload-plugins`) and check with `/obsidian-memory:vault doctor`.

The hooks ship with the plugin (`hooks/hooks.json`), so there's no need to edit `settings.json`.

> This plugin is for **Claude Code**. Claude Cowork doesn't run it reliably; a separate skill for Cowork is planned.

## Getting started

In your project, run `/obsidian-memory:vault init`. Claude asks two optional questions:

1. **Version the vault with git?** Commits are local, include only `obsidian-vault/` and are never pushed. If the project has no repository, one is created. If you say no and the project already uses git, `obsidian-vault/` is added to its `.gitignore`.
2. **Use Obsidian?** The vault is registered in Obsidian and opened. If Obsidian isn't installed, Claude offers to install it.

Answer no to both and you get just the vault folder. Then Claude explores the project and fills in `CLAUDE.md`. From the next session on, it starts with that context.

You can change your mind later with `init --git`, `--no-git`, `--obsidian` or `--no-obsidian`. The choices are stored in `obsidian-vault/.obsidian-memory.json`.

Projects without a vault are never touched: memory only starts with `init`.

**Upgrading from 1.3 or earlier:** the vault used to live in a hidden `.obsidian-vault/` folder. It's renamed to `obsidian-vault/` the first time the plugin runs in the project, together with the root `CLAUDE.md` import, the `.gitignore` entry and the Obsidian registration. Close Obsidian before the first session after upgrading, so it picks up the new path.

## How the context loads

| When | What happens |
|---|---|
| `init` | Adds `@obsidian-vault/CLAUDE.md` to the project's root `CLAUDE.md` |
| Session start | Claude Code loads the vault's `CLAUDE.md` through that import; the SessionStart hook adds the last session summary (or, if the last session wasn't summarized, the end of that conversation) and any alerts |
| During the session | Claude reads specs, decisions or older sessions only when the task needs them, and records new notes |
| Compaction / session end | Hooks archive the transcript into `daily/<date>/` and commit the vault (when git is on) |

## Usage

| Command | What it does |
|---|---|
| `/obsidian-memory:vault init` | Creates the vault, asking about git and Obsidian (both optional) |
| `/obsidian-memory:vault save` | Writes the session summary, updates Current State and commits the vault (when git is on) |
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

Hooks only act on projects that have a vault. Commits only happen when git is on.

## What's in the vault

```
obsidian-vault/
├── CLAUDE.md               # project context: Project, Tech Stack, Current State, Key Decisions, File Map, Do Not
├── _index.md               # generated index of every note
├── 00-inbox.md             # quick captures
├── daily/dd-mm-yyyy/       # session summaries; transcripts and memory snapshots (kept out of git)
├── specs/ plans/ processes/ decisions/ bugs/ retro/
├── templates/              # note templates for Obsidian's Templates plugin, only when Obsidian is on
├── .obsidian/              # Obsidian settings (Daily Notes, Templates), only when Obsidian is on
└── .obsidian-memory.json   # your init choices (git, obsidian)
```

## Guarantees

- Commits include **only** `obsidian-vault/`. Whatever you have staged is left untouched, and nothing is ever pushed.
- Transcripts and memory snapshots stay out of git (`obsidian-vault/.gitignore`).
- Before each commit, the script scans for secrets. If it finds any, it doesn't commit and shows an alert at the start of the next session.
- No vault is ever created in a project unless you run `init`, and never in your home folder, Downloads, Desktop, Documents, temp folders or a drive root.
- Nothing is installed and Obsidian is never restarted without your approval.
- If you open your whole project as an Obsidian vault, `obsidian-vault/` becomes a vault inside a vault, which Obsidian advises against. Open `obsidian-vault/` itself instead.

## Windows

- Install [Git for Windows](https://git-scm.com/downloads/win). The hooks run `bash scripts/vault …`, and Git Bash is what provides `bash`. Without it, the vault's `CLAUDE.md` still loads, but sessions aren't archived and the last session isn't injected. If Claude Code can't find Git Bash, set `CLAUDE_CODE_GIT_BASH_PATH` (for example `C:\Program Files\Git\bin\bash.exe`) in the `env` block of `settings.json`.
- The `scripts/vault` launcher tries `python3`, `python` and `py -3`, in that order, and skips the Microsoft Store shortcut that isn't a real Python.
- Everything is read and written as UTF-8.
- Obsidian is looked up in `%LOCALAPPDATA%\Programs\Obsidian`, and its configuration in `%APPDATA%\obsidian\obsidian.json`.

## Configuration (`scripts/vault.py`)

| Constant | Default |
|---|---|
| `VAULT_DIR` | `obsidian-vault` |
| `CONTEXT_LIMIT` | 12,000 characters injected |
| `SECRET_PATTERNS` | secret patterns checked before each commit |
| `OBSIDIAN_CONFIG` | initial `.obsidian/` settings (Daily Notes, Templates) |
| `excluded()` | folders where a vault is never created |

## License

MIT
