#!/usr/bin/env python3
"""Stop: when the main context has grown past a threshold, tell the user a free reset is ready.

/compact re-reads the whole conversation to summarise it; /clear costs nothing. With a current
checkpoint on disk, resume_from_checkpoint.py makes /clear lossless, so that's what we nudge
toward. Fires at most once per +25% growth per session. Stdlib only.
"""
import json, os, re, sys, time
from pathlib import Path

THRESHOLD = int(os.environ.get("CLAUDE_PLUGIN_OPTION_NUDGE_AT_TOKENS") or 100000)
FRESH_MIN = 20  # a checkpoint older than this is "stale" for the purpose of the nudge
STATE_DIR = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or (Path.home() / ".claude" / "expediter-state"))


def context_tokens(transcript):
    """Prompt size of the latest main-thread request: input + cache read + cache write."""
    try:
        lines = Path(transcript).read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0
    for line in reversed(lines[-400:]):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("type") != "assistant" or r.get("isSidechain"):
            continue
        u = (r.get("message") or {}).get("usage") or {}
        n = sum(int(u.get(k) or 0) for k in
                ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        if n:
            return n
    return 0


def newest_checkpoint(cwd):
    root = Path(cwd)
    c = list(root.glob(".scratch/checkpoint.md")) + list(root.glob(".scratch/*/checkpoint.md"))
    live = []
    for p in c:
        try:
            if re.search(r"status:\s*done\b", p.read_text(encoding="utf-8", errors="ignore")[:600]):
                continue
            live.append(p)
        except OSError:
            pass
    return max(live, key=lambda p: p.stat().st_mtime) if live else None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("stop_hook_active"):
        return 0
    n = context_tokens(data.get("transcript_path") or "")
    if n < THRESHOLD:
        return 0

    sid = data.get("session_id") or "unknown"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = STATE_DIR / f"nudge-{sid}.json"
    last = 0
    try:
        last = json.loads(state.read_text()).get("at", 0)
    except Exception:
        pass
    if last and n < last * 1.25:
        return 0
    state.write_text(json.dumps({"at": n, "ts": time.time()}))

    cp = newest_checkpoint(data.get("cwd") or os.getcwd())
    k = f"{n // 1000}k"
    if cp and (time.time() - cp.stat().st_mtime) / 60 <= FRESH_MIN:
        msg = (f"expediter: context is ~{k} tokens. Checkpoint is current ({cp}) — "
               f"/clear now is free and resumes from it automatically. "
               f"(/compact would re-read all {k} to summarise.)")
    else:
        msg = (f"expediter: context is ~{k} tokens. Run /expediter:checkpoint, then /clear — "
               f"cheaper than /compact, and the checkpoint is re-injected automatically.")
    print(json.dumps({"systemMessage": msg}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
