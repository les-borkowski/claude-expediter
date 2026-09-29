#!/usr/bin/env python3
"""SessionStart (clear|compact): re-inject the active checkpoint so work resumes cleanly.

Stdlib only, python 3.8+. Finds the most recently updated .scratch/**/checkpoint.md under the
session's working directory that isn't marked done and isn't stale, and prints it as context.
"""
import json, os, re, sys, time
from pathlib import Path

MAX_AGE_H = float(os.environ.get("CLAUDE_PLUGIN_OPTION_CHECKPOINT_MAX_AGE_HOURS") or 24)


def find_checkpoint(cwd):
    root = Path(cwd)
    cands = list(root.glob(".scratch/checkpoint.md")) + list(root.glob(".scratch/*/checkpoint.md"))
    live = []
    for p in cands:
        try:
            age_h = (time.time() - p.stat().st_mtime) / 3600
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if age_h > MAX_AGE_H:
            continue
        if re.search(r"status:\s*done\b", text[:600]):
            continue
        live.append((p.stat().st_mtime, p, text))
    if not live:
        return None, None
    live.sort(reverse=True)
    return live[0][1], live[0][2]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    source = data.get("source", "?")
    path, text = find_checkpoint(cwd)
    if not path:
        return 0
    msg = (
        f"[expediter] The conversation was just reset ({source}). You were in the middle of work "
        f"tracked in {path}. Resume from it:\n"
        "1. Treat the checkpoint below as authoritative over any summary above it.\n"
        "2. Before anything else, go through 'Tools to have running': run each check; restart what "
        "you can yourself (dev servers, background processes) from the worktree; for an MCP server "
        "whose tools are missing from your tool list, tell the user to reconnect it via /mcp and "
        "wait for them.\n"
        "3. Re-read handoff.md or ticket files only when the next step needs a detail from them.\n"
        "4. Continue from 'Next'. Keep updating this checkpoint as you go.\n\n"
        + text
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": msg}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
