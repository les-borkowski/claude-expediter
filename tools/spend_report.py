#!/usr/bin/env python3
"""Where does Claude Code usage go? By model, by orchestrator vs subagent, by agent type.

Stdlib only; runs on any python3. Reads ~/.claude/projects/**/*.jsonl locally.

    python3 tools/spend_report.py
    python3 tools/spend_report.py --since 2026-09-01
    python3 tools/spend_report.py --inspect      # show transcript structure if numbers look off
"""
import argparse, json
from collections import defaultdict, Counter
from pathlib import Path

# Relative weights, input = 1. Ratios, not prices: output ~5x, cache write ~1.25x, cache read ~0.1x.
W = {"input_tokens": 1.0, "cache_creation_input_tokens": 1.25,
     "cache_read_input_tokens": 0.1, "output_tokens": 5.0}
PINNED_TYPES = {"quick-lookup", "Explore", "feature-implementer", "test-writer", "code-reviewer",
                "frontend-dev", "docs-writer", "docs-fact-checker", "verifier"}
# Namespaced forms; "dev-loops:" is the plugin's former name, kept so older transcripts still match.
PINNED_TYPES |= {ns + t for t in list(PINNED_TYPES) for ns in ("expediter:", "dev-loops:")}


def weigh(u):
    return sum(W[k] * int(u.get(k) or 0) for k in W)


def short(model):
    m = (model or "unknown").replace("claude-", "")
    for fam in ("opus", "sonnet", "haiku", "fable"):
        if fam in m:
            return m
    return m


def agent_type_for(path, first_recs):
    """Best-effort agent type for a subagent transcript."""
    for r in first_recs:
        for k in ("agentType", "subagent_type", "agentName"):
            if r.get(k):
                return r[k]
    meta = path.with_suffix(".meta.json")
    if meta.exists():
        try:
            m = json.loads(meta.read_text())
            for k in ("agentType", "subagent_type", "type", "name"):
                if m.get(k):
                    return m[k]
        except Exception:
            pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--since", default="")
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args()

    by_model_thread = defaultdict(float)     # (thread, model) -> cost
    by_agent = defaultdict(lambda: defaultdict(float))  # agent_type -> model -> cost
    dispatch = Counter()                     # (subagent_type, model param) from main-thread Agent calls
    total = 0.0
    files = sorted(Path(a.root).rglob("*.jsonl"))
    keys_side, keys_main, names = Counter(), Counter(), Counter()

    for f in files:
        seen = set()
        recs = []
        for line in f.open(encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        if not recs:
            continue
        is_sub = any(r.get("isSidechain") for r in recs[:5]) or "subagent" in str(f).lower() or f.name.startswith("agent-")
        atype = agent_type_for(f, recs[:5]) if is_sub else None
        if a.inspect:
            (keys_side if is_sub else keys_main).update(k for r in recs[:3] for k in r.keys())
            names[("sub " if is_sub else "main ") + f.parent.name[:12] + "/" + f.name[:14]] += 1

        for r in recs:
            if a.since and (r.get("timestamp") or "") < a.since:
                continue
            if r.get("type") != "assistant":
                continue
            msg = r.get("message") or {}
            mid = msg.get("id")
            if mid in seen:
                continue            # streamed message split across records: count once
            if mid:
                seen.add(mid)
            c = weigh(msg.get("usage") or {})
            model = short(msg.get("model"))
            thread = "subagent" if (is_sub or r.get("isSidechain")) else "main"
            by_model_thread[(thread, model)] += c
            total += c
            if thread == "subagent":
                by_agent[atype or "(type unknown)"][model] += c
            else:
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in ("Agent", "Task"):
                        inp = b.get("input") or {}
                        st = inp.get("subagent_type") or "(none -> general-purpose)"
                        dispatch[(st, inp.get("model") or "inherit")] += 1

    if a.inspect:
        print(f"{len(files)} files. sample names:", list(names)[:8])
        print("main-thread record keys:", keys_main.most_common(25))
        print("subagent record keys:", keys_side.most_common(25))
        return

    if not total:
        raise SystemExit("no usage found")
    pct = lambda x: f"{100 * x / total:5.1f}%"

    print(f"{len(files)} transcript files, {total:,.0f} cost-weighted tokens\n")
    print("== by thread and model ==")
    for (th, m), c in sorted(by_model_thread.items(), key=lambda x: -x[1]):
        print(f"  {th:<9} {m:<22} {pct(c)}")
    main_c = sum(c for (th, _), c in by_model_thread.items() if th == "main")
    print(f"\n  orchestrator/main thread total {pct(main_c)}   subagents total {pct(total - main_c)}")

    print("\n== subagent spend by agent type ==")
    rows = sorted(by_agent.items(), key=lambda x: -sum(x[1].values()))
    for t, ms in rows[:15]:
        mix = ", ".join(f"{m} {100 * c / sum(ms.values()):.0f}%" for m, c in sorted(ms.items(), key=lambda x: -x[1]))
        flag = "" if t in PINNED_TYPES else "   <- not an expediter-pinned agent"
        print(f"  {t:<34} {pct(sum(ms.values()))}   [{mix}]{flag}")

    print("\n== dispatches from the main thread (subagent_type, model param) ==")
    for (st, m), n in dispatch.most_common(15):
        flag = "   <- inherits session model" if m == "inherit" and st not in PINNED_TYPES else ""
        print(f"  {n:>5}  {st:<34} model={m}{flag}")


if __name__ == "__main__":
    main()
