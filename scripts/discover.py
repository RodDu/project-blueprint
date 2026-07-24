#!/usr/bin/env python3
"""Skill Discovery Scanner — cross-platform, zero dependencies.

Detects installed AI agent platforms and scans known skill directories
to produce a JSON inventory report on stdout.

Usage:
    python discover.py                      # scan from cwd
    python discover.py --workspace /path    # scan from specific root
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# -- Known skill directories (relative to workspace or ~ home) -------------
SKILL_DIRS = {
    "antigravity_global": "~/.gemini/config/skills",
    "antigravity_cli": "~/.gemini/antigravity-cli/skills",
    "antigravity_plugins": "~/.gemini/config/plugins",
    "claude_global": "~/.claude/skills",
    "codex_global": "~/.agents/skills",
    "workspace_agents": ".agents/skills",
    "workspace_claude": ".claude/skills",
    "workspace_cursor": ".cursor/rules",
    "workspace_generic": "skills",
}

# -- Platform detection signals --------------------------------------------
PLATFORM_SIGNALS = {
    "antigravity": "~/.gemini",
    "claude_code": "~/.claude",
    "codex": "~/.codex",
    "cursor": "~/.cursor",
    "windsurf": "~/.windsurf",
    "aider": "~/.aider",
}

# -- Frontmatter regex (handles --- delimited YAML without pyyaml) ---------
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _expand(p: str) -> Path:
    """Expand ~ and env vars, return an absolute Path."""
    return Path(os.path.expanduser(os.path.expandvars(p)))


def detect_platforms() -> list[str]:
    """Return a list of AI agent platforms found on this machine."""
    return [name for name, sig in PLATFORM_SIGNALS.items() if _expand(sig).is_dir()]


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract key: value pairs from YAML frontmatter.

    Handles multiline block scalars (>-, >, |) by collecting indented
    continuation lines after the key declaration.
    """
    match = _FM_RE.match(text)
    if not match:
        return {}
    result: dict[str, str] = {}
    lines = match.group(1).splitlines()
    current_key = None
    current_val_parts: list[str] = []
    for line in lines:
        # New key: value line (not indented)
        kv = re.match(r"^(\w[\w\-]*):\s*(.*)", line)
        if kv:
            # Flush previous key
            if current_key is not None:
                result[current_key] = " ".join(current_val_parts).strip()
            current_key = kv.group(1)
            val = kv.group(2).strip().strip('"').strip("'")
            # Skip block scalar indicators — the real value is on continuation lines
            if val in (">-", ">", "|", "|+", "|-", ">+"):
                current_val_parts = []
            else:
                current_val_parts = [val] if val else []
        elif current_key is not None and (line.startswith("  ") or line.startswith("\t")):
            # Indented continuation line
            current_val_parts.append(line.strip())
    # Flush last key
    if current_key is not None:
        result[current_key] = " ".join(current_val_parts).strip()
    return result


def scan_skill_dir(base: Path, source: str) -> list[dict]:
    """Scan a single directory for SKILL.md files (one level deep)."""
    skills = []
    if not base.is_dir():
        return skills
    for child in sorted(base.iterdir()):
        skill_file = child / "SKILL.md" if child.is_dir() else None
        if skill_file and skill_file.is_file():
            try:
                fm = parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                fm = {}
            skills.append({
                "name": fm.get("name", child.name),
                "description": fm.get("description", ""),
                "path": str(child),
                "source": source,
            })
    return skills


def run_scan(workspace: Path) -> dict:
    """Execute the full discovery scan and return the report dict."""
    all_skills: list[dict] = []

    for source, raw_path in SKILL_DIRS.items():
        is_workspace = not raw_path.startswith("~")
        base = (workspace / raw_path) if is_workspace else _expand(raw_path)
        all_skills.extend(scan_skill_dir(base, source))

    return {
        "platform": detect_platforms(),
        "skills": all_skills,
        "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_count": len(all_skills),
    }


# -- CLI entry point -------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Discover installed AI-agent skills.")
    parser.add_argument(
        "--workspace", type=Path, default=Path.cwd(),
        help="Workspace root for relative skill dirs (default: cwd)",
    )
    args = parser.parse_args()
    report = run_scan(args.workspace.resolve())
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
