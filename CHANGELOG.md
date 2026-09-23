# Changelog

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
