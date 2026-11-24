#!/usr/bin/env python3
"""PreToolUse(Agent): while a feature under this session's cwd has a PAUSE flag, refuse new agent
dispatches and point the driver at its pause steps. Stdlib only, python 3.8+.

`slots.py pause` writes <worktree>/.scratch/<slug>/PAUSE; `slots.py resume` removes it. A driver
can be one long turn, so a message might not reach it; its next dispatch always does.
"""
import json, sys
from pathlib import Path


def decide(event):
    cwd = event.get("cwd")
    if not cwd:
        return None
    flags = []
    try:
        # a driver may have cd'd into a subfolder: walk up, but stop at its own checkout root
        # (a worktree has a .git file) so a session never sees a nested worktree's flag
        here = Path(cwd).resolve()
        for d in [here, *here.parents]:
            flags = sorted(d.glob(".scratch/*/PAUSE"))
            if flags or (d / ".git").exists():
                break
    except OSError:
        return None
    if not flags:
        return None
    slug = flags[0].parent.name
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"expediter: PAUSE requested for {slug} — dispatch nothing new; follow "
            "'On a pause message' in /drive-tickets."),
    }}


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    out = decide(event)
    if out:
        print(json.dumps(out))
    return 0


# ---- self-test -------------------------------------------------------------------------------

def _feature(flagged):
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / ".scratch" / "f").mkdir(parents=True)
    if flagged:
        (d / ".scratch" / "f" / "PAUSE").write_text("x")
    return d


def test_gate_denies_when_flagged():
    out = decide({"cwd": str(_feature(True)), "tool_name": "Agent"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "PAUSE requested for f" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_gate_allows_unflagged():
    assert decide({"cwd": str(_feature(False)), "tool_name": "Agent"}) is None


def test_gate_no_cwd_allows():
    assert decide({"tool_name": "Agent"}) is None
    assert decide({"cwd": "Z:/does/not/exist", "tool_name": "Agent"}) is None


def test_gate_scoped_to_own_cwd():
    # main checkout session must not be blocked by a paused worktree nested under it
    import tempfile
    main_ = Path(tempfile.mkdtemp())
    wt = main_ / ".claude" / "worktrees" / "feature-x" / ".scratch" / "x"
    wt.mkdir(parents=True); (wt / "PAUSE").write_text("x")
    assert decide({"cwd": str(main_), "tool_name": "Agent"}) is None


def test_gate_denies_from_a_subfolder():
    d = _feature(True); (d / ".git").write_text("gitdir: x")
    sub = d / "frontend" / "src"; sub.mkdir(parents=True)
    out = decide({"cwd": str(sub), "tool_name": "Agent"})
    assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny"


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
        for n, f in tests:
            try:
                f()
            except Exception as e:
                print(f"FAIL {n}: {type(e).__name__}: {e}")
                sys.exit(1)
        print(f"ok {len(tests)}")
        sys.exit(0)
    sys.exit(main())
