#!/usr/bin/env python3
"""obsidian-memory: per-project Obsidian vault as extended memory for Claude Code.

Each project gets <project-root>/obsidian-vault/ (visible; older vaults in .obsidian-vault/ are renamed):
  CLAUDE.md          AI context file (Project, Tech Stack, Current State, Key Decisions, File Map, Do Not)
  _index.md          generated index of every note
  00-inbox.md        quick captures
  daily/<dd-mm-yyyy>/session-HHhMM.md             curated session summary (written by Claude)
  daily/<dd-mm-yyyy>/transcript-HHhMM-<id>.md     raw transcript (hooks; not in git)
  daily/<dd-mm-yyyy>/memory/*.md                  snapshot of Claude's auto-memory (not in git)
  specs/ plans/ processes/ decisions/ bugs/ retro/
  templates/         note templates for Obsidian (only when Obsidian is on; Claude falls back to the plugin's)
  .obsidian/         pre-configured Obsidian settings

Project root = nearest ancestor of cwd that already has a vault, else the git top-level, else cwd.

Subcommands:
  info    [--cwd DIR]                          paths as JSON (creates nothing)
  status  [--cwd DIR]                          human-readable status (always exits 0)
  init    [--cwd DIR] [--name N] [--no-git|--git] [--no-obsidian|--obsidian]
                                               create/repair the vault; git and Obsidian are optional
                                               (choices saved in obsidian-vault/.obsidian-memory.json)
  save    [--cwd DIR] [-m MSG]                 regenerate index and commit the vault (if git is on)
  open    [--cwd DIR] [--restart]              register the vault in Obsidian and open it
  index   [--cwd DIR]                          regenerate _index.md
  doctor                                       check requirements (python, git, Obsidian) and how to install
  install git|python|obsidian                  install one requirement (ask the user first!)
  archive                                      SessionEnd / PreCompact hook (JSON on stdin; only projects with a vault)
  context                                      SessionStart hook (JSON on stdin)
"""
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from urllib.parse import quote

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_SRC = os.path.join(PLUGIN_ROOT, "templates")
VAULT_DIR = "obsidian-vault"
LEGACY_VAULT_DIRS = [".obsidian-vault"]  # hidden name used up to 1.4.0; renamed to VAULT_DIR on first touch
DATE_FMT = "%d-%m-%Y"
FOLDERS = ["daily", "specs", "plans", "processes", "decisions", "bugs", "retro"]
HOME = os.path.expanduser("~")
CONTEXT_LIMIT = 12000
STATE_FILE = ".state.json"
SETTINGS_FILE = ".obsidian-memory.json"  # choices made at init (git, obsidian) and the user's time zone
FALLBACK_IDENTITY = ["-c", "user.name=Obsidian Memory", "-c", "user.email=obsidian-memory@localhost"]

REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
TAG_BLOCK_RE = re.compile(r"<(command-[a-z-]+|local-command-[a-z]+)>.*?</\1>", re.S)

SECRET_PATTERNS = [
    ("sk- key (OpenAI/Anthropic)", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("GitHub token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Google token", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("assigned credential", re.compile(
        r"(?i)\b(password|passwd|senha|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*['\"]?[^\s'\"`]{8,}")),
]

CLAUDE_TEMPLATE = """# Project

{name} — _(what it is, who it's for and its goal; 2 to 4 sentences)_

## Tech Stack

| Layer | Tool |
|---|---|
| _(to fill in)_ | |

## Current State

> Update this section every time you return after a break. Thirty seconds here saves five minutes of re-orientation.

**Last updated:** {today}

### Working
- `obsidian-vault/` created

### Broken / Blocked
- None

### Focus right now
- _(to fill in)_

## Key Decisions Made

These are settled. Do not reopen them without a good reason (details in `decisions/`).

- _(to fill in)_

## File Map

```
{name}/
├── CLAUDE.md                 # Imports @obsidian-vault/CLAUDE.md (native loading)
├── obsidian-vault/           # Obsidian knowledge base
│   ├── CLAUDE.md             # ← AI context file (you are here)
│   ├── _index.md             # Generated index of every note
│   ├── 00-inbox.md           # Unprocessed notes and quick captures
│   ├── daily/                # One folder per day (dd-mm-yyyy), one file per session
│   ├── specs/                # Feature specs before coding starts
│   ├── plans/                # Implementation plans and roadmaps
│   ├── processes/            # Processes, runbooks, recurring procedures
│   ├── decisions/            # Architectural decisions (ADRs)
│   ├── bugs/                 # Bug reports and investigation notes
│   └── retro/                # Retrospectives and lessons learned
└── _(fill in with the project structure)_
```

## Do Not

**Stop. Read the linked decision record before suggesting any change in these areas.**

- _(a preencher)_
"""

GITIGNORE_LINES = [
    ".obsidian/workspace*.json",
    ".obsidian/cache",
    ".obsidian/plugins/",
    STATE_FILE,
    "daily/**/transcript-*.md",
    "daily/**/memory/",
    "daily/**/memoria/",  # legacy name
]

OBSIDIAN_CONFIG = {
    "core-plugins.json": {p: True for p in [
        "file-explorer", "global-search", "switcher", "graph", "backlink", "outgoing-link", "tag-pane",
        "properties", "page-preview", "daily-notes", "templates", "note-composer", "command-palette",
        "editor-status", "bookmarks", "outline", "word-count", "file-recovery"]},
    "daily-notes.json": {"folder": "daily", "format": "DD-MM-YYYY/[day]", "template": "templates/daily-note"},
    "templates.json": {"folder": "templates", "dateFormat": "DD-MM-YYYY", "timeFormat": "HH:mm"},
    "app.json": {"alwaysUpdateLinks": True},
}

ROOT_IMPORT = "@%s/CLAUDE.md" % VAULT_DIR
ROOT_BLOCK = ("\n## Project memory (Obsidian)\n\n"
              "Context, current state, decisions and history live in `%s/`. "
              "Keep them up to date with the obsidian-memory plugin.\n\n%s\n" % (VAULT_DIR, ROOT_IMPORT))


# ---------------------------------------------------------------- utils

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
OBSIDIAN_DOWNLOAD = "https://obsidian.md/download"


def uopen(p, mode="r"):
    """UTF-8 everywhere (Windows defaults to cp1252)."""
    return open(p, mode, encoding="utf-8")


def sh(args, cwd=None, timeout=20):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)


def read_json(p, default):
    try:
        with uopen(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(p, data):
    with uopen(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def emit(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------- project / vault

def run_git_root(cwd):
    code, out, _ = sh(["git", "-C", cwd, "rev-parse", "--show-toplevel"], timeout=5)
    return out if code == 0 and out else None


def _rewrite(path, old_name):
    """Point references to old_name/ in a text file (root CLAUDE.md, project .gitignore) at VAULT_DIR/.
    A rewritten line that already exists in the file is dropped (a .gitignore listing both names)."""
    if not os.path.exists(path):
        return
    with uopen(path) as f:
        txt = f.read()
    pat = re.compile(r"(?<![.\w-])%s(?=/|$)" % re.escape(old_name))
    existing = set(l.strip() for l in txt.splitlines() if not pat.search(l))
    lines = []
    for line in txt.splitlines(True):
        if pat.search(line):
            line = pat.sub(VAULT_DIR, line)
            if line.strip() and line.strip() in existing:
                continue
            existing.add(line.strip())
        lines.append(line)
    new = "".join(lines)
    if new != txt:
        with uopen(path, "w") as f:
            f.write(new)


def migrate_legacy(root):
    """Rename an old vault folder to VAULT_DIR and fix what pointed at it."""
    new = os.path.join(root, VAULT_DIR)
    for old_name in LEGACY_VAULT_DIRS:
        old = os.path.join(root, old_name)
        if os.path.isdir(old) and not os.path.exists(new):
            os.rename(old, new)
            _rewrite(os.path.join(root, "CLAUDE.md"), old_name)   # @import
            # The vault's CLAUDE.md is prose: a blind rename turns notes about the migration itself into
            # contradictions ("still in obsidian-vault/, will move to obsidian-vault/"). Claude fixes it instead.
            save_state(new, migrated_from=old_name)
            _rewrite(os.path.join(root, ".gitignore"), old_name)  # vault kept out of git
            cfgp = obsidian_config_path()                         # Obsidian registration
            cfg = read_json(cfgp, {})
            real_old = os.path.normcase(os.path.realpath(old))
            for meta in (cfg.get("vaults") or {}).values():
                if os.path.normcase(meta.get("path", "")) == real_old:
                    meta["path"] = os.path.realpath(new)
                    write_json(cfgp, cfg)
                    break


def project_root(cwd=None):
    cwd = os.path.realpath(os.path.abspath(cwd or os.getcwd()))
    d = cwd
    while True:
        for name in [VAULT_DIR] + LEGACY_VAULT_DIRS:
            if os.path.isfile(os.path.join(d, name, "CLAUDE.md")):
                migrate_legacy(d)
                return d
        parent = os.path.dirname(d)
        if parent == d or d == HOME:
            break
        d = parent
    return run_git_root(cwd) or cwd


def excluded(root):
    """Folders where a vault is never created automatically (home, OS folders, temp, drive roots)."""
    real = os.path.normcase(os.path.realpath(root))
    bad = {os.path.normcase(os.path.realpath(p)) for p in (
        HOME, "/", "/tmp", "/private/tmp", tempfile.gettempdir(),
        os.path.join(HOME, "Downloads"), os.path.join(HOME, "Desktop"), os.path.join(HOME, "Documents"))}
    if real in bad or os.path.dirname(real) == real:  # drive root (C:\) or /
        return True
    prefixes = [os.path.join(HOME, ".claude"), tempfile.gettempdir(), "/tmp", "/private/tmp"]
    return any(real.startswith(os.path.normcase(os.path.realpath(p)) + os.sep) for p in prefixes)


def paths(root):
    v = os.path.join(root, VAULT_DIR)
    now = dt.datetime.now()
    return {
        "project_root": root,
        "project": os.path.basename(root.rstrip("/")),
        "vault": v,
        "claude_md": os.path.join(v, "CLAUDE.md"),
        "vault_exists": os.path.isfile(os.path.join(v, "CLAUDE.md")),
        # the vault's own templates (created with Obsidian, may be customized), else the plugin's
        "templates": os.path.join(v, "templates") if os.path.isdir(os.path.join(v, "templates")) else TEMPLATES_SRC,
        "today_dir": os.path.join(v, "daily", now.strftime(DATE_FMT)),
        "today": now.strftime(DATE_FMT),
        "session_suffix": now.strftime("%Hh%M"),
    }


def load_state(v):
    return read_json(os.path.join(v, STATE_FILE), {})


def save_state(v, **kw):
    s = load_state(v)
    s.update(kw)
    write_json(os.path.join(v, STATE_FILE), s)


def load_settings(v):
    """Choices made at init. Missing keys keep the behavior of older vaults (git and Obsidian on)."""
    s = read_json(os.path.join(v, SETTINGS_FILE), {})
    return {"git": s.get("git", True), "obsidian": s.get("obsidian", True)}


def save_settings(v, **kw):
    p = os.path.join(v, SETTINGS_FILE)
    s = read_json(p, {})
    s.update(kw)
    write_json(p, s)


def local_timezone():
    """IANA name of this machine's time zone (e.g. Europe/Lisbon), or None when it can't be told (Windows)."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" in tz and not tz.startswith("/"):
        return tz
    target = os.path.realpath("/etc/localtime")
    if "zoneinfo/" in target:
        return target.split("zoneinfo/", 1)[1]
    try:
        with uopen("/etc/timezone") as f:
            return f.read().strip() or None
    except OSError:
        return None


def ensure_timezone(v):
    """Record the user's time zone once, so tools without a local clock (Cowork) write local times."""
    if read_json(os.path.join(v, SETTINGS_FILE), {}).get("timezone"):
        return
    tz = local_timezone()
    if tz:
        save_settings(v, timezone=tz)


def has_root_import(root):
    try:
        with uopen(os.path.join(root, "CLAUDE.md")) as f:
            return any(line.strip() == ROOT_IMPORT for line in f)
    except OSError:
        return False


def ensure_root_import(root):
    """Make <root>/CLAUDE.md import the vault CLAUDE.md so Claude Code loads it natively."""
    if has_root_import(root):
        return
    p = os.path.join(root, "CLAUDE.md")
    existing = ""
    if os.path.exists(p):
        with uopen(p) as f:
            existing = f.read()
    with uopen(p, "w") as f:
        f.write(existing.rstrip() + "\n" + ROOT_BLOCK if existing.strip() else ROOT_BLOCK.lstrip())


def ensure_gitignore(v):
    gi = os.path.join(v, ".gitignore")
    lines = []
    if os.path.exists(gi):
        with uopen(gi) as f:
            lines = f.read().splitlines()
    missing = [l for l in GITIGNORE_LINES if l not in lines]
    if missing:
        with uopen(gi, "w") as f:
            f.write("\n".join([l for l in lines if l.strip()] + missing) + "\n")


def ensure_obsidian_config(v):
    od = os.path.join(v, ".obsidian")
    os.makedirs(od, exist_ok=True)
    for name, data in OBSIDIAN_CONFIG.items():
        p = os.path.join(od, name)
        if not os.path.exists(p):
            write_json(p, data)


def ensure_templates(v):
    td = os.path.join(v, "templates")
    os.makedirs(td, exist_ok=True)
    if os.path.isdir(TEMPLATES_SRC):
        for n in os.listdir(TEMPLATES_SRC):
            dst = os.path.join(td, n)
            if n.endswith(".md") and not os.path.exists(dst):
                shutil.copy2(os.path.join(TEMPLATES_SRC, n), dst)


def init_vault(root, name=None, obsidian=True):
    v = os.path.join(root, VAULT_DIR)
    ensure_root_import(root)
    for f in FOLDERS:
        fdir = os.path.join(v, f)
        os.makedirs(fdir, exist_ok=True)
        if not os.listdir(fdir):
            uopen(os.path.join(fdir, ".gitkeep"), "w").close()
    cm = os.path.join(v, "CLAUDE.md")
    if not os.path.exists(cm):
        with uopen(cm, "w") as f:
            f.write(CLAUDE_TEMPLATE.format(name=name or os.path.basename(root.rstrip("/")),
                                           today=dt.date.today().strftime(DATE_FMT)))
    inbox = os.path.join(v, "00-inbox.md")
    if not os.path.exists(inbox):
        with uopen(inbox, "w") as f:
            f.write("# Inbox\n\nQuick captures. Move them to specs/, plans/, decisions/ or bugs/ when it makes sense.\n\n")
    ensure_gitignore(v)
    if obsidian:  # Obsidian's settings and its Templates folder only when the user uses Obsidian
        ensure_obsidian_config(v)
        ensure_templates(v)
    build_index(v)
    return v


# ---------------------------------------------------------------- git

def has_git():
    return shutil.which("git") is not None


def is_git(root):
    return has_git() and run_git_root(root) is not None


def git_identity(root):
    code, out, _ = sh(["git", "-C", root, "config", "user.email"])
    return [] if code == 0 and out else FALLBACK_IDENTITY


def scan_secrets(root, pathspecs):
    """Scan lines being added (staged diff) for secret-looking strings."""
    _, diff, _ = sh(["git", "-C", root, "diff", "--cached", "-U0", "--no-color", "--"] + pathspecs, timeout=30)
    hits, current = [], None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+"):
            for label, rx in SECRET_PATTERNS:
                if rx.search(line):
                    hits.append({"file": current, "type": label})
                    break
    return hits


def git_commit(root, message, extra_paths=None):
    """Commit only the vault (plus extra_paths); never touches other staged work."""
    v = os.path.join(root, VAULT_DIR)
    if not load_settings(v)["git"]:
        return {"git": "disabled"}  # the user chose not to version the vault
    if not has_git():
        return {"git": "not-installed"}
    if not is_git(root):
        return {"git": "no-repository"}
    if sh(["git", "-C", root, "check-ignore", "-q", v])[0] == 0:
        return {"git": "vault-ignored-by-project"}  # the project chose to keep its vault out of git
    ensure_gitignore(v)  # keeps older vaults up to date (e.g. .obsidian/plugins/)
    specs = [v] + [p for p in (extra_paths or []) if os.path.exists(p)]
    for old_name in LEGACY_VAULT_DIRS:  # after a rename, commit the old path's removal too
        old = os.path.join(root, old_name)
        if not os.path.exists(old) and sh(["git", "-C", root, "ls-files", "--", old])[1]:
            specs.append(old)
            root_md = os.path.join(root, "CLAUDE.md")  # its @import was rewritten by the rename
            if os.path.exists(root_md) and root_md not in specs:
                specs.append(root_md)
    code, _, err = sh(["git", "-C", root, "add", "-A", "--"] + specs)
    if code != 0:
        return {"git": "error", "detail": err}
    _, changed, _ = sh(["git", "-C", root, "diff", "--cached", "--name-only", "--"] + specs)
    if not changed:
        return {"git": "no-changes"}
    hits = scan_secrets(root, specs)
    if hits:
        sh(["git", "-C", root, "reset", "-q", "--"] + specs)
        save_state(v, blocked_commit={"when": dt.datetime.now().strftime("%d-%m-%Y %H:%M"), "findings": hits})
        return {"git": "blocked-by-secret", "findings": hits}
    code, _, err = sh(["git", "-C", root] + git_identity(root) + ["commit", "-q", "-m", message, "--"] + specs)
    if code != 0:
        return {"git": "error", "detail": err}
    _, sha, _ = sh(["git", "-C", root, "rev-parse", "--short", "HEAD"])
    save_state(v, last_commit={"sha": sha, "msg": message, "when": dt.datetime.now().strftime("%d-%m-%Y %H:%M")},
               blocked_commit=None)
    return {"git": "commit", "sha": sha, "files": len(changed.splitlines())}


def git_init(root):
    if not has_git():
        return "git-not-installed"
    if is_git(root):
        return "existing"
    if excluded(root):
        return "skipped-excluded-folder"
    code, _, err = sh(["git", "init", "-q", root])
    return "initialized" if code == 0 else "error: " + err


def ignore_vault_in_project(root):
    """Keep the vault out of the project's git (the user opted out of versioning it)."""
    if sh(["git", "-C", root, "check-ignore", "-q", os.path.join(root, VAULT_DIR)])[0] == 0:
        return "already-ignored"
    p = os.path.join(root, ".gitignore")
    existing = ""
    if os.path.exists(p):
        with uopen(p) as f:
            existing = f.read()
    with uopen(p, "w") as f:
        f.write((existing.rstrip() + "\n\n" if existing.strip() else "")
                + "# obsidian-memory: the vault is kept out of git (chosen at init)\n%s/\n" % VAULT_DIR)
    return "added"


# ---------------------------------------------------------------- obsidian

def obsidian_config_path():
    if IS_MAC:
        return os.path.join(HOME, "Library", "Application Support", "obsidian", "obsidian.json")
    if IS_WIN:
        return os.path.join(os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming")), "obsidian", "obsidian.json")
    candidates = [
        os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "obsidian", "obsidian.json"),
        os.path.join(HOME, ".var", "app", "md.obsidian.Obsidian", "config", "obsidian", "obsidian.json"),  # flatpak
        os.path.join(HOME, "snap", "obsidian", "current", ".config", "obsidian", "obsidian.json"),        # snap
    ]
    return next((c for c in candidates if os.path.exists(c)), candidates[0])


def obsidian_app_path():
    """Where the Obsidian Desktop app is installed, or None."""
    if IS_MAC:
        for c in ("/Applications/Obsidian.app", os.path.join(HOME, "Applications", "Obsidian.app")):
            if os.path.isdir(c):
                return c
        code, out, _ = sh(["mdfind", "kMDItemCFBundleIdentifier == 'md.obsidian'"], timeout=5)
        return out.splitlines()[0] if code == 0 and out else None
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
        for base in (os.path.join(local, "Programs", "Obsidian"), os.path.join(local, "Obsidian"),
                     os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Obsidian")):
            exe = os.path.join(base, "Obsidian.exe")
            if os.path.isfile(exe):
                return exe
        return None
    for name in ("obsidian", "Obsidian"):
        found = shutil.which(name)
        if found:
            return found
    if sh(["flatpak", "info", "md.obsidian.Obsidian"], timeout=5)[0] == 0:
        return "flatpak:md.obsidian.Obsidian"
    if sh(["snap", "list", "obsidian"], timeout=5)[0] == 0:
        return "snap:obsidian"
    for d in ("/opt/Obsidian", os.path.join(HOME, "Applications")):
        if os.path.isdir(d):
            for n in os.listdir(d):
                if n.lower().startswith("obsidian"):
                    return os.path.join(d, n)
    return None


def obsidian_installed():
    return obsidian_app_path() is not None


def obsidian_running():
    if IS_WIN:
        _, out, _ = sh(["tasklist", "/FI", "IMAGENAME eq Obsidian.exe", "/NH"])
        return "obsidian.exe" in out.lower()
    code, _, _ = sh(["pgrep", "-x", "Obsidian" if IS_MAC else "obsidian"])
    return code == 0


def open_url(url):
    try:
        if IS_WIN:
            os.startfile(url)  # noqa: registered protocol / default browser
            return True, ""
        code, _, err = sh(["open", url] if IS_MAC else ["xdg-open", url])
        return code == 0, err
    except OSError as e:
        return False, str(e)


def open_download_page():
    try:
        return webbrowser.open(OBSIDIAN_DOWNLOAD)
    except Exception:
        return False


def obsidian_vault_id(vault_path):
    cfg = read_json(obsidian_config_path(), {})
    real = os.path.normcase(os.path.realpath(vault_path))
    for vid, meta in (cfg.get("vaults") or {}).items():
        if os.path.normcase(os.path.realpath(meta.get("path", ""))) == real:
            return vid
    return None


def obsidian_open_uri(vid):
    return open_url("obsidian://open?vault=%s&file=CLAUDE" % quote(vid))


def obsidian_register(vault_path):
    cfgp = obsidian_config_path()
    cfg = read_json(cfgp, {})
    backup = cfgp + ".bak-obsidian-memory"
    if os.path.exists(cfgp) and not os.path.exists(backup):
        shutil.copy2(cfgp, backup)
    real = os.path.realpath(vault_path)
    vid = hashlib.md5(real.encode("utf-8")).hexdigest()[:16]
    cfg.setdefault("vaults", {})[vid] = {"path": real, "ts": int(time.time() * 1000)}
    os.makedirs(os.path.dirname(cfgp), exist_ok=True)
    write_json(cfgp, cfg)
    return vid


def obsidian_quit():
    if IS_WIN:
        sh(["taskkill", "/IM", "Obsidian.exe"])          # graceful close (no /F)
    elif IS_MAC:
        sh(["osascript", "-e", 'quit app "Obsidian"'])
    else:
        sh(["pkill", "-x", "obsidian"])
    for _ in range(30):
        if not obsidian_running():
            return True
        time.sleep(0.5)
    return False


def cmd_open(root, restart=False):
    v = os.path.join(root, VAULT_DIR)
    if not os.path.isfile(os.path.join(v, "CLAUDE.md")):
        return {"obsidian": "no-vault", "message": "Run init first."}
    ensure_obsidian_config(v)
    ensure_templates(v)
    if not obsidian_installed():
        opened = open_download_page()
        return {"obsidian": "not-installed", "download_page_opened": opened, "url": OBSIDIAN_DOWNLOAD,
                "install": install_plan().get("obsidian"),
                "message": "Obsidian not found. The download page was opened; it can also be installed with "
                           "the package manager (ask the user first). Then run open."}
    vid = obsidian_vault_id(v)
    if vid:
        ok, err = obsidian_open_uri(vid)
        return {"obsidian": "opened" if ok else "error", "vault_id": vid, "detail": err or None}
    if obsidian_running():
        if not restart:
            return {"obsidian": "needs-restart",
                    "message": "The vault isn't registered yet and Obsidian is running. Registering requires closing and "
                               "reopening Obsidian. Ask the user; if they agree, run: open --restart"}
        if not obsidian_quit():
            return {"obsidian": "error", "message": "Could not close Obsidian. Close it and run open again."}
    vid = obsidian_register(v)
    time.sleep(0.5)
    ok, err = obsidian_open_uri(vid)
    return {"obsidian": "registered-and-opened" if ok else "registered-open-failed", "vault_id": vid,
            "detail": err or None}


# ---------------------------------------------------------------- requirements (doctor / install)

def package_manager():
    if IS_WIN:
        return "winget" if shutil.which("winget") else None
    if IS_MAC:
        return "brew" if shutil.which("brew") else None
    for pm in ("apt", "dnf", "pacman", "zypper"):
        if shutil.which(pm):
            return pm
    return None


def install_plan():
    """Install command per missing requirement, for this OS. 'auto' = can run without sudo/password."""
    pm = package_manager()
    if IS_WIN:
        wg = ["winget", "install", "-e", "--source", "winget", "--accept-package-agreements",
              "--accept-source-agreements", "--id"]
        return {
            "git": {"cmd": wg + ["Git.Git"], "auto": pm == "winget", "manual": "https://git-scm.com/downloads/win"},
            "python": {"cmd": wg + ["Python.Python.3.12"], "auto": pm == "winget", "manual": "https://www.python.org/downloads/"},
            "obsidian": {"cmd": wg + ["Obsidian.Obsidian"], "auto": pm == "winget", "manual": OBSIDIAN_DOWNLOAD},
        }
    if IS_MAC:
        brew = pm == "brew"
        return {
            "git": {"cmd": ["brew", "install", "git"] if brew else ["xcode-select", "--install"], "auto": True,
                    "manual": "https://git-scm.com/download/mac"},
            "python": {"cmd": ["brew", "install", "python"] if brew else ["xcode-select", "--install"], "auto": True,
                       "manual": "https://www.python.org/downloads/"},
            "obsidian": {"cmd": ["brew", "install", "--cask", "obsidian"] if brew else None, "auto": brew,
                         "manual": OBSIDIAN_DOWNLOAD},
        }
    sudo_cmd = {"apt": ["sudo", "apt", "install", "-y"], "dnf": ["sudo", "dnf", "install", "-y"],
                "pacman": ["sudo", "pacman", "-S", "--noconfirm"], "zypper": ["sudo", "zypper", "install", "-y"]}.get(pm)
    flatpak = shutil.which("flatpak")
    return {
        "git": {"cmd": sudo_cmd + ["git"] if sudo_cmd else None, "auto": False, "manual": "https://git-scm.com/download/linux"},
        "python": {"cmd": sudo_cmd + ["python3"] if sudo_cmd else None, "auto": False, "manual": "https://www.python.org/downloads/"},
        "obsidian": {"cmd": ["flatpak", "install", "-y", "--user", "flathub", "md.obsidian.Obsidian"] if flatpak else None,
                     "auto": bool(flatpak), "manual": OBSIDIAN_DOWNLOAD},
    }


def cmd_doctor(root):
    code, gitv, _ = sh(["git", "--version"])
    _, gname, _ = sh(["git", "config", "--global", "user.name"])
    _, gmail, _ = sh(["git", "config", "--global", "user.email"])
    app = obsidian_app_path()
    plan = install_plan()
    checks = {
        "platform": sys.platform,
        "python": {"ok": True, "version": sys.version.split()[0], "executable": sys.executable},
        "git": {"ok": code == 0, "version": gitv or None},
        "git_identity": {"ok": bool(gname and gmail), "name": gname or None, "email": gmail or None},
        "obsidian": {"ok": app is not None, "app": app, "running": obsidian_running() if app else False,
                     "config": obsidian_config_path()},
        "package_manager": package_manager(),
        "project": root,
    }
    if IS_WIN:
        checks["git_bash"] = {"ok": bool(os.environ.get("MSYSTEM") or shutil.which("bash")),
                              "hint": "The hooks need Git Bash (ships with Git for Windows)."}
    missing = [k for k in ("git", "obsidian") if not checks[k]["ok"]]
    if IS_WIN and not checks["git_bash"]["ok"] and "git" not in missing:
        missing.append("git")
    checks["missing"] = missing
    checks["how_to_install"] = {k: {"command": " ".join(plan[k]["cmd"]) if plan[k]["cmd"] else None,
                                    "automatic": plan[k]["auto"], "manual": plan[k]["manual"]} for k in missing}
    if not checks["git_identity"]["ok"]:
        checks["recommended"] = 'git config --global user.name "Your Name" && git config --global user.email "you@example.com"'
    return checks


def cmd_install(item):
    """Run the install for one requirement. Claude must ask the user BEFORE calling this."""
    plan = install_plan().get(item)
    if not plan:
        return {"error": "unknown item: %s (use git, python or obsidian)" % item}
    if not plan["cmd"] or not plan["auto"]:
        opened = False
        if not plan["cmd"] or item == "obsidian":  # no package manager: official installer / download page
            opened = open_url(plan["manual"])[0]
        return {"installed": False, "reason": "needs manual action (sudo, password or no package manager)",
                "command_for_user": " ".join(plan["cmd"]) if plan["cmd"] else None, "manual": plan["manual"],
                "download_page_opened": opened}
    code, out, err = sh(plan["cmd"], timeout=900)
    return {"installed": code == 0, "command": " ".join(plan["cmd"]), "output": (out or err)[-1500:],
            "note": "Reopen the terminal/Claude Code if the new command isn't found." if code == 0 else None}


# ---------------------------------------------------------------- transcript

def local_time(ts):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return dt.datetime.now().astimezone()


# Commands that say nothing about the work; a session with only these isn't archived.
TRIVIAL_COMMANDS = {"/exit", "/quit", "/clear", "/resume", "/config", "/help", "/status", "/cost", "/model",
                    "/login", "/logout", "/doctor", "/compact", "/context", "/permissions", "/hooks", "/plugin"}


def clean_text(s):
    """Plain text of a message; a slash command becomes `/name args` so command-only sessions still count."""
    s = REMINDER_RE.sub("", s)
    cmd = ""
    m = re.search(r"<command-name>(.*?)</command-name>", s, re.S)
    if m and m.group(1).strip() not in TRIVIAL_COMMANDS:
        a = re.search(r"<command-args>(.*?)</command-args>", s, re.S)
        args = a.group(1).strip() if a else ""
        cmd = "`%s%s`" % (m.group(1).strip(), " " + args if args else "")
    rest = TAG_BLOCK_RE.sub("", s).strip()
    return "\n\n".join(x for x in (cmd, rest) if x)


def answer_text(entry):
    """The user's answers to a question tool (AskUserQuestion); other tool results are skipped."""
    r = entry.get("toolUseResult")
    answers = r.get("answers") if isinstance(r, dict) else None
    if not isinstance(answers, dict):
        return ""
    return "; ".join("%s → %s" % (q, a) for q, a in answers.items())[:600]


def render_transcript(path):
    """Return (start_datetime, markdown_body, n_user_msgs)."""
    start, lines, n_user = None, [], 0
    with uopen(path) as f:
        for raw in f:
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            if e.get("type") not in ("user", "assistant") or e.get("isSidechain") or e.get("isMeta"):
                continue
            if start is None and e.get("timestamp"):
                start = local_time(e["timestamp"])
            content = (e.get("message") or {}).get("content")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
            role = e["type"]
            out = []
            for b in blocks:
                bt = b.get("type")
                if bt == "text":
                    t = clean_text(b.get("text", ""))
                    if t:
                        out.append(t)
                elif bt == "tool_result" and role == "user":
                    t = answer_text(e)
                    if t:
                        out.append("> 💬 %s" % t)
                elif bt == "tool_use" and role == "assistant":
                    inp = b.get("input") or {}
                    hint = inp.get("description") or inp.get("file_path") or inp.get("command") or inp.get("skill") or ""
                    hint = str(hint).splitlines()[0][:160] if hint else ""
                    out.append("> 🔧 `%s` %s" % (b.get("name"), hint))
            if not out:
                continue
            when = local_time(e.get("timestamp", "")).strftime("%H:%M")
            if role == "user":
                n_user += 1
                lines.append("### 🧑 User · %s\n\n%s\n" % (when, "\n\n".join(out)))
            else:
                lines.append("### 🤖 Claude · %s\n\n%s\n" % (when, "\n\n".join(out)))
    return start or dt.datetime.now().astimezone(), "\n".join(lines), n_user


def cmd_archive():
    data = json.load(sys.stdin)
    tpath = data.get("transcript_path")
    sid = data.get("session_id", "session")
    cwd = data.get("cwd") or os.getcwd()
    reason = data.get("reason") or data.get("trigger") or data.get("hook_event_name", "")
    if not tpath or not os.path.exists(tpath):
        return
    root = project_root(cwd)
    if not os.path.isfile(os.path.join(root, VAULT_DIR, "CLAUDE.md")):
        return  # memory is opt-in: only projects that ran init get archived
    start, body, n_user = render_transcript(tpath)
    if n_user == 0:
        return
    v = init_vault(root, obsidian=load_settings(os.path.join(root, VAULT_DIR))["obsidian"])
    ensure_timezone(v)
    day = start.strftime(DATE_FMT)
    ddir = os.path.join(v, "daily", day)
    os.makedirs(ddir, exist_ok=True)
    fname = "transcript-%s-%s.md" % (start.strftime("%Hh%M"), sid[:8])
    with uopen(os.path.join(ddir, fname), "w") as f:
        f.write(
            "---\ntype: transcript\ndate: %s\nsession_id: %s\ncwd: \"%s\"\nreason: %s\ntags: [claude/transcript]\n---\n\n"
            "# Transcript %s · %s\n\nContext: [[CLAUDE]]\n\n%s\n"
            % (day, sid, cwd, reason, day, start.strftime("%H:%M"), body)
        )
    mem = os.path.join(os.path.dirname(tpath), "memory")
    if os.path.isdir(mem):
        mdir = os.path.join(ddir, "memory")
        os.makedirs(mdir, exist_ok=True)
        for n in os.listdir(mem):
            if n.endswith(".md"):
                shutil.copy2(os.path.join(mem, n), os.path.join(mdir, n))
    build_index(v)
    save_state(v, last_archive={"when": dt.datetime.now().strftime("%d-%m-%Y %H:%M"), "reason": reason})
    git_commit(root, "vault: session %s %s (%s)" % (day, start.strftime("%H:%M"), reason or "end"))


# ---------------------------------------------------------------- index / context / status

def build_index(v):
    def dkey(d):
        try:
            return dt.datetime.strptime(d, DATE_FMT)
        except ValueError:
            return dt.datetime.min

    out = ["---\ntype: index\ntags: [claude/index]\n---\n", "# Index\n",
           "_Generated automatically on %s. Do not edit by hand._\n" % dt.datetime.now().strftime("%d-%m-%Y %H:%M"),
           "- [[CLAUDE]] — project context", "- [[00-inbox]] — inbox\n"]
    for folder in FOLDERS:
        fdir = os.path.join(v, folder)
        if not os.path.isdir(fdir):
            continue
        if folder == "daily":
            days = sorted((d for d in os.listdir(fdir) if os.path.isdir(os.path.join(fdir, d))), key=dkey, reverse=True)
            if not days:
                continue
            out.append("## daily\n")
            for d in days:
                notes = sorted(n[:-3] for n in os.listdir(os.path.join(fdir, d)) if n.endswith(".md"))
                out.append("- **%s** — %s" % (d, " · ".join("[[daily/%s/%s|%s]]" % (d, n, n) for n in notes) or "_empty_"))
            out.append("")
        else:
            notes = sorted(n[:-3] for n in os.listdir(fdir) if n.endswith(".md"))
            if notes:
                out.append("## %s\n" % folder)
                out.extend("- [[%s/%s|%s]]" % (folder, n, n) for n in notes)
                out.append("")
    with uopen(os.path.join(v, "_index.md"), "w") as f:
        f.write("\n".join(out) + "\n")


def latest_session(v):
    ddir = os.path.join(v, "daily")
    best = None
    if os.path.isdir(ddir):
        for d in os.listdir(ddir):
            try:
                day = dt.datetime.strptime(d, DATE_FMT)
            except ValueError:
                continue
            for n in os.listdir(os.path.join(ddir, d)):
                if n.startswith(("session-", "sessao-")) and n.endswith(".md"):  # sessao- = legacy
                    key = (day, n)
                    if best is None or key > best[0]:
                        best = (key, os.path.join(ddir, d, n))
    return best[1] if best else None


def read_capped(p, limit):
    with uopen(p) as f:
        t = f.read()
    return t if len(t) <= limit else t[:limit] + "\n…(truncado — leia o arquivo completo)"


def alerts(v):
    b = load_state(v).get("blocked_commit")
    if not b:
        return ""
    items = "; ".join("%s in %s" % (h["type"], h["file"]) for h in b.get("findings", []))
    return ("\n\n⚠️ The last automatic vault commit (%s) was BLOCKED by a possible secret: %s. "
            "Tell the user, remove the secret and run save." % (b.get("when"), items))


def latest_transcript(v):
    """Newest archived transcript (raw, written by the hooks), or None."""
    best = None
    ddir = os.path.join(v, "daily")
    if os.path.isdir(ddir):
        for d in os.listdir(ddir):
            sub = os.path.join(ddir, d)
            if os.path.isdir(sub):
                for n in os.listdir(sub):
                    if n.startswith("transcript-") and n.endswith(".md"):
                        f = os.path.join(sub, n)
                        if best is None or os.path.getmtime(f) > os.path.getmtime(best):
                            best = f
    return best


def transcript_tail(p, limit):
    """The end of a transcript, starting at a message boundary."""
    with uopen(p) as f:
        t = f.read()
    if len(t) <= limit:
        return t
    t = t[-limit:]
    i = t.find("\n### ")
    return "…\n" + (t[i + 1:] if i >= 0 else t)


def cmd_context():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    source = data.get("source", "")
    p = paths(project_root(data.get("cwd")))
    if p["vault_exists"]:
        v = p["vault"]
        last = latest_session(v)
        tr = latest_transcript(v)
        # A raw transcript newer than the last summary means that session ended without a summary.
        if tr and last and os.path.getmtime(tr) <= os.path.getmtime(last):
            tr = None
        history = []
        if last:
            history.append("\n\n=== Last session summary: %s ===\n%s" % (last, read_capped(last, 6000)))
        if tr:
            history.append("\n\n=== End of the latest conversation, not summarized yet: %s ===\n%s"
                           % (tr, transcript_tail(tr, 5000)))
        ctx = ("This project has an Obsidian vault at %s (project memory). Its CLAUDE.md is already in your context%s. "
               "Use this to resume, and to answer questions such as \"where did we leave off?\", without reading "
               "the vault with tools. Use the obsidian-memory plugin to write to the vault."
               % (v, ", and so is what happened last (below)" if history else "; there is no session history yet"))
        if has_root_import(p["project_root"]) and source != "compact":
            ctx += "\n(%s is already loaded via @import in the root CLAUDE.md.)" % p["claude_md"]
        else:
            ctx += "\n\n=== %s ===\n%s" % (p["claude_md"], read_capped(p["claude_md"], CONTEXT_LIMIT))
        ctx += "".join(history)
        if tr:
            ctx += ("\n\nThe latest conversation has no summary. When you save this session, cover it too.")
        if source == "compact":
            ctx += ("\n\nThe conversation was just compacted (the full transcript is already archived). "
                    "At the end of your next response, record in today's session-*.md and in Current State what was "
                    "done before the compaction, using the compaction summary.")
        ctx += alerts(v)
        st = load_state(v)
        moved = st.pop("migrated_from", None)
        if moved:
            ctx += ("\n\nThe vault folder was just renamed from %s/ to %s/ (automatic migration). Its CLAUDE.md "
                    "was left as is: before anything else, edit it so paths say %s/ and notes about the pending "
                    "migration say it is done; then tell the user in one line." % (moved, VAULT_DIR, VAULT_DIR))
            write_json(os.path.join(v, STATE_FILE), st)  # notify once
    else:
        ctx = ("obsidian-memory: this project (%s) has no %s/, so project memory is off. "
               "Don't bring it up unless the user asks about memory; to turn it on, use /obsidian-memory:vault init."
               % (p["project_root"], VAULT_DIR))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))


def cmd_status(root):
    p = paths(root)
    v = p["vault"]
    out = ["Project: %s" % root, "Vault: %s (%s)" % (v, "exists" if p["vault_exists"] else "does NOT exist — run init")]
    settings = load_settings(v)
    if p["vault_exists"] and not settings["git"]:
        out.append("Git: off (chosen at init; the vault is not committed)")
    elif not has_git():
        out.append("Git: not installed")
    elif is_git(root):
        _, branch, _ = sh(["git", "-C", root, "branch", "--show-current"])
        _, last, _ = sh(["git", "-C", root, "log", "-1", "--format=%h %cr — %s", "--", v])
        _, pend, _ = sh(["git", "-C", root, "status", "--porcelain", "--", v])
        out.append("Git: branch %s · last vault commit: %s · pending vault changes: %d"
                   % (branch or "?", last or "none", len(pend.splitlines()) if pend else 0))
    else:
        out.append("Git: no repository (init creates one)")
    if p["vault_exists"] and not settings["obsidian"]:
        out.append("Obsidian: off (chosen at init; the vault is plain Markdown)")
    elif obsidian_installed():
        vid = obsidian_vault_id(v) if p["vault_exists"] else None
        out.append("Obsidian: %s · app %s" % ("vault registered" if vid else "vault not registered",
                                              "running" if obsidian_running() else "closed"))
    else:
        out.append("Obsidian: not installed (run doctor / open to open the download page)")
    if p["vault_exists"]:
        tz = read_json(os.path.join(v, SETTINGS_FILE), {}).get("timezone")
        out.append("Time zone: %s" % (tz or "not recorded yet (set on the next save)"))
        out.append("Last session: %s" % (latest_session(v) or "none"))
        s = load_state(v)
        if s.get("last_archive"):
            out.append("Last automatic archive: %(when)s (%(reason)s)" % s["last_archive"])
        a = alerts(v).strip()
        if a:
            out.append(a)
    out.append("Today: folder %s · suffix %s" % (p["today_dir"], p["session_suffix"]))
    print("\n".join(out))


# ---------------------------------------------------------------- main

def pop_opt(args, flag, has_value=True):
    if flag in args:
        i = args.index(flag)
        if not has_value:
            del args[i]
            return True
        val = args[i + 1]
        del args[i:i + 2]
        return val
    return None if has_value else False


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
        except (AttributeError, ValueError):
            pass
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args.pop(0)
    if cmd == "archive":
        cmd_archive()
        return
    if cmd == "context":
        cmd_context()
        return
    root = project_root(pop_opt(args, "--cwd"))
    if cmd == "info":
        info = paths(root)
        if info["vault_exists"]:
            info["settings"] = load_settings(info["vault"])
            info["settings"]["timezone"] = read_json(os.path.join(info["vault"], SETTINGS_FILE), {}).get("timezone")
        emit(info)
    elif cmd == "status":
        try:
            cmd_status(root)
        except Exception as e:  # never fail the skill's context injection
            print("status unavailable: %s" % e)
    elif cmd == "init":
        name = pop_opt(args, "--name")
        no_git, want_git = pop_opt(args, "--no-git", False), pop_opt(args, "--git", False)
        no_obs, want_obs = pop_opt(args, "--no-obsidian", False), pop_opt(args, "--obsidian", False)
        result = {"project_root": root}
        if excluded(root):
            result["warning"] = "Excluded folder (home, Downloads, Desktop, Documents, tmp). Use --cwd with the project folder."
            emit(result)
            return
        created = not os.path.isfile(os.path.join(root, VAULT_DIR, "CLAUDE.md"))
        result["vault_created"] = created
        # A new vault takes the flags as given; an existing one keeps its choices unless a flag changes them.
        settings = {"git": True, "obsidian": True} if created else load_settings(os.path.join(root, VAULT_DIR))
        if no_git or want_git:
            settings["git"] = bool(want_git and not no_git)
        if no_obs or want_obs:
            settings["obsidian"] = bool(want_obs and not no_obs)
        v = result["vault"] = init_vault(root, name, obsidian=settings["obsidian"])
        save_settings(v, **settings)
        ensure_timezone(v)
        result["settings"] = settings
        if settings["git"]:
            result["git_init"] = git_init(root)
            result.update(git_commit(root, "vault: init obsidian-memory", [os.path.join(root, "CLAUDE.md")]))
        else:
            result["git"] = "disabled"
            if is_git(root):
                result["project_gitignore"] = ignore_vault_in_project(root)
        if settings["obsidian"]:
            result.update(cmd_open(root))
        else:
            result["obsidian"] = "disabled"
        emit(result)
    elif cmd == "save":
        msg = pop_opt(args, "-m") or "vault: save %s" % dt.datetime.now().strftime("%d-%m-%Y %H:%M")
        v = os.path.join(root, VAULT_DIR)
        if not os.path.isfile(os.path.join(v, "CLAUDE.md")):
            emit({"error": "no vault; run init"})
            return
        ensure_timezone(v)
        build_index(v)
        emit(git_commit(root, msg))
    elif cmd == "open":
        emit(cmd_open(root, restart=pop_opt(args, "--restart", False)))
    elif cmd == "doctor":
        emit(cmd_doctor(root))
    elif cmd == "install":
        emit(cmd_install(args[0] if args else ""))
    elif cmd == "index":
        v = os.path.join(root, VAULT_DIR)
        build_index(v)
        print(os.path.join(v, "_index.md"))
    else:
        sys.exit("unknown command: %s" % cmd)


if __name__ == "__main__":
    main()
