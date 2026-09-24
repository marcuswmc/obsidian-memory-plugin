# Changelog

## obsidian-memory-cowork 1.0.1 — 24-09-2026
- Explicit time zone: the vault stores the user's IANA zone as `timezone` in `.obsidian-memory.json`, and session notes, day folders and `Last updated` use it. Cowork may run on a remote machine in UTC, so the skill no longer trusts the machine's clock: it asks for the zone once when it isn't set, computes the time with `TZ=<zone> date`, and falls back to UTC plus the zone's offset when the machine doesn't know the zone.

## obsidian-memory-cowork 1.0.0 — 24-09-2026
- New companion plugin for Claude Cowork in `cowork/`, listed in the same marketplace. A single skill resumes from `obsidian-vault/` (CLAUDE.md and the latest session note), records decisions and notes, saves the session and can create a vault without git or Obsidian, using file tools only. It never runs git and steps aside when the Claude Code plugin is active.

## 1.4.1 — 24-09-2026
- Fix: migrating from `.obsidian-vault/` left a duplicate `obsidian-vault/` line in a `.gitignore` that listed both names.
- Fix: migration no longer rewrites the vault's `CLAUDE.md` word by word, which turned notes about the migration itself into contradictions. The next SessionStart tells Claude, once, to update the paths and the migration notes.

## 1.4.0 — 24-09-2026
- The vault folder is now visible: `obsidian-vault/` (was `.obsidian-vault/`, hidden by Finder and file explorers). Existing vaults are renamed on first use, and the root `CLAUDE.md` import, the project's `.gitignore` entry and the Obsidian registration are updated. With git on, the rename is committed.
- Claude Code only: Cowork support (1.3.0 and 1.3.1) was removed. Cowork will get a separate skill.
- `init` asks before creating a vault: whether to version it with git and whether to use Obsidian, both optional. With neither, only the vault folder is created. The choices are saved in `obsidian-vault/.obsidian-memory.json` and can be changed with `init --git`, `--no-git`, `--obsidian` or `--no-obsidian`.
- Declining git in a project that already uses it adds `obsidian-vault/` to the project's `.gitignore`; `save` and the hooks never commit.
- Installing git or Obsidian uses the system package manager (Homebrew, winget, apt/dnf, flatpak) with the user's approval. Without one, the official installer or download page opens. No package manager is ever installed.
- A vault is no longer created automatically at session end: projects without a vault are left untouched until `init`.
- SessionStart tells Claude the vault context is already loaded, so it resumes without reading files. When the latest session ended without a summary, it injects the end of that conversation.
- Fix: sessions whose only user input was a slash command (such as `init`) or answers to questions were not archived. Commands and answers are now kept in the transcript.
- `.obsidian/` and `templates/` are only created when Obsidian is on (or when `open` is run). Without them, Claude uses the plugin's own note templates; a vault's `templates/` still takes precedence, so customized templates keep working.

## 1.3.1 — 23-09-2026
- Remote Cowork sessions: hooks may not run there and the script may not reach the selected folder. The skill now loads at the start of a session when an attached folder has `.obsidian-vault/` but no vault context was injected, reads `CLAUDE.md` and the latest session with file tools, and saves the session note before the end (committing later if the script can't run).

## 1.3.0 — 23-09-2026
- Claude Cowork support: when running inside a Cowork session, the project is the folder the user selected for the session (read from the session metadata), not Cowork's `outputs/` folder.
- Fix: a Cowork session with no selected folder no longer creates a vault inside Cowork's internal session folders; memory stays off and SessionStart says so.
- In Cowork, SessionStart injects the full `.obsidian-vault/CLAUDE.md`, since Cowork doesn't load the project's root `CLAUDE.md`.

## 1.2.1 — 23-09-2026
- Fix: when a project ignores its own `.obsidian-vault/` in `.gitignore`, the vault commit is skipped (`vault-ignored-by-project`) instead of failing with an error on every save and session end.

## 1.2.0 — 23-09-2026
- Everything in English: README, skill instructions, script messages and JSON keys, note templates, generated `CLAUDE.md` model and manifests.
- Renamed files: `session-*.md` (was `sessao-*.md`), `memory/` (was `memoria/`), templates `decision`, `plan`, `process`, `session`, `daily-note`. Older vaults keep working: `sessao-*.md` is still read as a session and `memoria/` stays out of git.
- Note content follows the user's conversation language.

## 1.1.0 — 23-09-2026
- Windows (via Git Bash) and Linux support: `scripts/vault` launcher that finds `python3`, `python` or `py -3`; per-OS Obsidian paths, processes and URIs; UTF-8 for every read and write.
- Detects the Obsidian Desktop app; if it's missing, opens the download page.
- New `doctor` (checks python, git, git identity, Obsidian and Git Bash) and `install git|python|obsidian` commands (always with the user's approval).
- `marketplace.json` for installing straight from GitHub.
- `.obsidian/plugins/` kept out of git (third-party code and possible tokens in `data.json`); older vaults get the updated `.gitignore` on their next commit.

## 1.0.0 — 23-09-2026
- Plugin with SessionStart, PreCompact and SessionEnd hooks; `vault` skill (init, save, status, open); templates; pre-configured `.obsidian/`; commits of the vault only, with a secret scan.
