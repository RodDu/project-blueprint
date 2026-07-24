#!/usr/bin/env python3
"""Skill Installer — install skills from registry or GitHub URL.

Usage:
    python install.py ponytail                            # from registry
    python install.py https://github.com/user/repo        # from URL
    python install.py ponytail --scope workspace           # workspace-local
    python install.py ponytail --scope global              # user-global
    python install.py ponytail --platform claude           # target Claude Code
    python install.py --list                               # list registry
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# -- Target directories per platform and scope -----------------------------
TARGET_DIRS = {
    "antigravity": {"global": "~/.gemini/config/skills", "workspace": "skills"},
    "claude":      {"global": "~/.claude/skills",        "workspace": ".claude/skills"},
    "codex":       {"global": "~/.agents/skills",        "workspace": ".agents/skills"},
    "cursor":      {"global": "~/.cursor/rules",         "workspace": ".cursor/rules"},
}

PLATFORM_SIGNALS = {
    "antigravity": "~/.gemini",
    "claude":      "~/.claude",
    "codex":       "~/.codex",
    "cursor":      "~/.cursor",
}

SCRIPT_DIR = Path(__file__).resolve().parent
REGISTRY_FILE = SCRIPT_DIR / "registry.json"


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(p)))


def _err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"✓ {msg}")


# -- Platform detection ----------------------------------------------------
def detect_platform() -> str:
    """Return the first detected platform, or 'antigravity' as fallback."""
    for name, sig in PLATFORM_SIGNALS.items():
        if _expand(sig).is_dir():
            return name
    return "antigravity"


# -- Registry helpers ------------------------------------------------------
def load_registry() -> dict:
    if not REGISTRY_FILE.is_file():
        _err(f"Registry not found: {REGISTRY_FILE}")
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))


def list_registry() -> None:
    reg = load_registry()
    print(f"Skill Registry v{reg['version']}  ({len(reg['skills'])} skills)\n")
    for s in reg["skills"]:
        src = "builtin" if s["source"] == "builtin" else "local" if s["source"] == "local" else "git"
        print(f"  {s['name']:<30} [{src:>7}]  {s['description']}")


def find_in_registry(name: str) -> dict | None:
    reg = load_registry()
    return next((s for s in reg["skills"] if s["name"] == name), None)


# -- Git helpers -----------------------------------------------------------
def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        _err("git is not installed or not on PATH.")
    except subprocess.TimeoutExpired:
        _err("git operation timed out (120 s).")


def clone_and_copy(repo_url: str, path_in_repo: str, dest: Path) -> None:
    """Shallow-clone repo to temp dir, copy the skill subfolder to dest."""
    with tempfile.TemporaryDirectory(prefix="skill_") as tmp:
        tmp_path = Path(tmp)
        result = _git("clone", "--depth=1", repo_url, str(tmp_path / "repo"))
        if result.returncode != 0:
            _err(f"git clone failed:\n{result.stderr.strip()}")

        src = tmp_path / "repo" / path_in_repo
        if not src.is_dir():
            _err(f"Path '{path_in_repo}' not found in repository.")

        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)


# -- Validation ------------------------------------------------------------
def validate_install(dest: Path) -> bool:
    skill_md = dest / "SKILL.md"
    if not skill_md.is_file():
        print(f"WARNING: SKILL.md not found at {dest}", file=sys.stderr)
        return False
    return True


# -- Resolve target directory ----------------------------------------------
def resolve_dest(name: str, platform: str, scope: str, workspace: Path) -> Path:
    dirs = TARGET_DIRS.get(platform)
    if not dirs:
        _err(f"Unknown platform: {platform}")
    raw = dirs[scope]
    base = _expand(raw) if scope == "global" else workspace / raw
    return base / name


# -- Main install logic ----------------------------------------------------
def install_skill(source: str, platform: str, scope: str, workspace: Path) -> None:
    is_url = source.startswith("http://") or source.startswith("https://")

    if is_url:
        # Direct URL install — clone entire repo as a skill folder
        name = source.rstrip("/").split("/")[-1].removesuffix(".git")
        dest = resolve_dest(name, platform, scope, workspace)
        print(f"Installing from URL → {dest}")
        clone_and_copy(source, ".", dest)
    else:
        # Registry lookup
        entry = find_in_registry(source)
        if not entry:
            _err(f"Skill '{source}' not found in registry. Run --list to see available skills.")
        if entry["source"] in ("builtin", "local"):
            _err(f"Skill '{source}' is {entry['source']} and cannot be installed remotely.")
        dest = resolve_dest(entry["name"], platform, scope, workspace)
        print(f"Installing '{entry['name']}' → {dest}")
        clone_and_copy(entry["source"], entry.get("path_in_repo", entry["name"]), dest)

    if validate_install(dest):
        _ok(f"Installed successfully at {dest}")
    else:
        print("⚠ Installed but SKILL.md is missing — skill may not work.", file=sys.stderr)


# -- CLI entry point -------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Install AI-agent skills.")
    parser.add_argument("source", nargs="?", help="Skill name or GitHub URL")
    parser.add_argument("--list", action="store_true", help="List registry skills")
    parser.add_argument("--scope", choices=["global", "workspace"], default="global")
    parser.add_argument("--platform", choices=["antigravity", "claude", "codex", "cursor", "auto"], default="auto")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()

    if args.list:
        list_registry()
        return

    if not args.source:
        parser.print_help()
        sys.exit(1)

    platform = detect_platform() if args.platform == "auto" else args.platform
    install_skill(args.source, platform, args.scope, args.workspace.resolve())


if __name__ == "__main__":
    main()
