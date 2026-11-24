#!/usr/bin/env python3
"""Dev-server slot ledger shared by parallel expediter drivers. Stdlib only, python 3.8+.

  slots.py acquire <slug> --ports name=base[,name=base...] [--max N] [--worktree PATH]
  slots.py release <slug> [--worktree PATH]
  slots.py status [--worktree PATH]
  slots.py --self-test
"""
import argparse, contextlib, json, os, re, shlex, socket, subprocess, sys, time
from pathlib import Path

GRACE_S = 30 * 60      # an unlistened slot survives this long after acquire / last checkpoint write
LOCK_STALE_S = 30
FULL = 3               # exit code when the repo's cap is reached


def ledger_path():
    env = os.environ.get("EXPEDITER_SLOTS_FILE")
    return Path(env) if env else Path.home() / ".claude" / "expediter" / "slots.json"


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(path):
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + 60
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE_S:
                    lock.unlink()  # left behind by a crashed process
                    continue
            except OSError:
                continue
            if time.time() > deadline:
                raise SystemExit(f"slots: could not lock {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


def listening(port):
    # dev servers on Windows often bind "localhost" to ::1 only (Vite), so probe both stacks
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family) as s:
                s.settimeout(0.2)
                if s.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            pass
    return False


def _checkpoint(worktree, slug):
    return Path(worktree) / ".scratch" / slug / "checkpoint.md"


def is_stale(entry, slug, now, listening):
    if not Path(entry["worktree"]).is_dir():
        return True
    cp = _checkpoint(entry["worktree"], slug)
    try:
        text, mtime = cp.read_text(encoding="utf-8", errors="ignore"), cp.stat().st_mtime
    except OSError:
        return True
    if any(listening(p) for p in entry["ports"].values()):
        return False  # a running app keeps its slot, even for a finished feature: it still uses RAM
    if re.search(r"status:\s*done\b", text[:600]):
        return True
    return now - max(entry["acquired"], mtime) > GRACE_S


def reclaim(data, repo, now, listening):
    slots = data.get(repo, {})
    for slug in [s for s, e in slots.items() if is_stale(e, s, now, listening)]:
        del slots[slug]


def acquire(data, repo, slug, worktree, max_n, bases, now, listening):
    slots = data.setdefault(repo, {})
    if slug in slots:
        return slots[slug]["ports"]
    reclaim(data, repo, now, listening)
    if len(slots) >= max_n:
        return None
    # ports held by any repo count: two repos with the same base ports must not share one
    taken = {p for r in data.values() for e in r.values() for p in e["ports"].values()}
    k = 1
    while any(b + k in taken or listening(b + k) for b in bases.values()):
        k += 1
    ports = {n: b + k for n, b in bases.items()}
    slots[slug] = {"worktree": str(worktree), "offset": k, "ports": ports, "acquired": now}
    return ports


def release(data, repo, slug):
    data.get(repo, {}).pop(slug, None)


# ---- CLI ---------------------------------------------------------------------------------------

def _git(worktree, *args):
    r = subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"slots: git {' '.join(args)} failed in {worktree}: {r.stderr.strip()}")
    return r.stdout.strip()


def repo_key(worktree):
    common = Path(_git(worktree, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = Path(worktree) / common
    return os.path.normcase(os.path.realpath(common))


def _parse_ports(spec):
    out = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, _, base = part.partition("=")
        if not name or not base.isdigit():
            raise SystemExit(f"slots: bad --ports entry {part!r}; expected name=base")
        out[name] = int(base)
    if not out:
        raise SystemExit("slots: --ports is empty")
    return out


def _norm(p):
    return os.path.normcase(os.path.realpath(p))


def drivers(cmd=("claude", "agents", "--json")):
    """Live Claude sessions: normalised cwd -> state. None when `claude agents` can't be read."""
    try:
        r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=15)
        rows = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return {_norm(e["cwd"]): e.get("state") or {"busy": "working"}.get(e.get("status"), e.get("status") or "unknown")
            for e in rows if isinstance(e, dict) and e.get("cwd")}


NOT_LIVE = {"stopped", "done", "failed"}


def feature_rows(wts, slots, live):
    rows = []
    for wt in wts:
        for cp in sorted(Path(wt).glob(".scratch/*/checkpoint.md")):
            slug = cp.parent.name
            text = cp.read_text(encoding="utf-8", errors="ignore")
            st = re.search(r"status:\s*(\S+)", text[:600])
            status = st.group(1) if st else "?"
            cur = re.search(r"## Current task\s*\n+(.+)", text)
            done_sec = re.search(r"## Completed\s*\n(.*?)(?:\n## |\Z)", text, re.S)
            done = len(re.findall(r"^- ", done_sec.group(1), re.M)) if done_sec else 0
            issues = cp.parent / "issues"
            total = len(list(issues.glob("*.md"))) if issues.is_dir() else 0
            if live is None:
                driver = "unknown"
            else:
                driver = live.get(_norm(wt), "stopped")
            if status == "done":
                state = "done"
            elif status == "paused":
                state = "paused"
            elif (cp.parent / "PAUSE").exists():
                state = "pausing"
            elif status == "blocked":
                state = "waiting on you"
            else:
                state = driver
            held = slots.get(slug)
            rows.append({"slug": slug, "worktree": str(wt), "status": status, "driver": driver,
                         "state": state, "current": cur.group(1).strip() if cur else "",
                         "done": done, "total": total, "ports": held["ports"] if held else None,
                         "updated": cp.stat().st_mtime})
    return rows


def _flag(row):
    return Path(row["worktree"]) / ".scratch" / row["slug"] / "PAUSE"


def pause(rows):
    flagged = []
    for r in rows:
        flag = _flag(r)
        if r["status"] != "done" and not flag.is_symlink():
            flag.write_text("pause requested\n", encoding="utf-8")
            flagged.append(r["slug"])
    return flagged


SAFE_SLUG = re.compile(r"[A-Za-z0-9._-]+")


def launch_line(row):
    # the line is run by a shell: a slug comes from a folder name, so refuse anything but plain names
    if not SAFE_SLUG.fullmatch(row["slug"]):
        return None
    return (f'cd {shlex.quote(row["worktree"])} && claude --bg --name {row["slug"]} --model sonnet '
            f'--advisor opus "/expediter:drive-tickets {row["slug"]}"')


def resume(rows):
    lines = []
    for r in rows:
        with contextlib.suppress(OSError):
            _flag(r).unlink()
        if r["status"] != "done" and r["driver"] in NOT_LIVE:
            lines.append(launch_line(r) or f"# skipped {r['slug']!r}: not a plain feature name")
    return lines


def _worktrees(worktree):
    return [l[9:] for l in _git(worktree, "worktree", "list", "--porcelain").splitlines()
            if l.startswith("worktree ")]


def _status(data, repo, worktree, now, as_json=False):
    reclaim(data, repo, now, listening)
    slots = data.get(repo, {})
    rows = feature_rows(_worktrees(worktree), slots, drivers())
    warnings = []
    # an unaccounted listener in a slot range is an orphaned server still using RAM; report, never kill
    held_ports = {p for e in slots.values() for p in e["ports"].values()}
    bases = {}
    for e in slots.values():
        for n, p in e["ports"].items():
            bases[n] = p - e["offset"]
    top = max([e["offset"] for e in slots.values()] + [0]) + 2
    for n, b in bases.items():
        for k in range(1, top + 1):
            if b + k not in held_ports and listening(b + k):
                warnings.append(f"port {b + k} ({n}, slot {k}) is listening but no feature holds it")
    if as_json:
        print(json.dumps({"repo": repo, "features": rows, "warnings": warnings}, indent=2))
        return
    print(f"repo: {repo}")
    for r in rows:
        ports = ", ".join(f"{n}={p}" for n, p in r["ports"].items()) if r["ports"] else "no slot"
        print(f"  {r['slug']:<26} {r['state']:<15} {r['done']}/{r['total']:<4} {ports:<26} "
              f"{r['current'][:50]}")
    if not rows:
        print("  (no features)")
    for w in warnings:
        print(f"  WARNING: {w}")
    # an unaccounted listener in a slot range is an orphaned server still using RAM; report, never kill
    held_ports = {p for e in slots.values() for p in e["ports"].values()}
    bases = {}
    for e in slots.values():
        for n, p in e["ports"].items():
            bases[n] = p - e["offset"]
    top = max([e["offset"] for e in slots.values()] + [0]) + 2
    for n, b in bases.items():
        for k in range(1, top + 1):
            if b + k not in held_ports and listening(b + k):
                print(f"  WARNING: port {b + k} ({n}, slot {k}) is listening but no feature holds it")


def main(argv):
    ap = argparse.ArgumentParser(prog="slots.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("acquire"); a.add_argument("slug")
    a.add_argument("--ports", required=True); a.add_argument("--max", type=int, default=2)
    r = sub.add_parser("release"); r.add_argument("slug")
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true")
    pa = sub.add_parser("pause"); re_ = sub.add_parser("resume")
    for p in (a, r, s, pa, re_):
        p.add_argument("--worktree", default=os.getcwd())
    args = ap.parse_args(argv)

    wt = os.path.realpath(args.worktree)
    if args.cmd in ("pause", "resume"):
        live = drivers() if args.cmd == "resume" else {}
        rows = feature_rows(_worktrees(wt), {}, live)
        if args.cmd == "pause":
            flagged = pause(rows)
            print("pause requested for: " + (", ".join(flagged) or "nothing (all done)"))
        else:
            if live is None:
                raise SystemExit("slots: can't read `claude agents --json`; is `claude` on PATH?")
            lines = resume(rows)
            print("\n".join(lines) if lines else "nothing to relaunch")
        return 0
    repo, f, now = repo_key(wt), ledger_path(), time.time()
    with locked(f):
        data = load(f)
        if args.cmd == "acquire":
            ports = acquire(data, repo, args.slug, wt, args.max, _parse_ports(args.ports), now, listening)
            save(f, data)
            if ports is None:
                print(f"full: {args.max} slot(s) held for this repo:")
                for slug, e in data[repo].items():
                    print(f"  {slug}  {e['worktree']}  {e['ports']}")
                return FULL
            for n, p in ports.items():
                print(f"{n}={p}")
        elif args.cmd == "release":
            release(data, repo, args.slug)
            save(f, data)
        else:
            _status(data, repo, wt, now, args.json)
            save(f, data)
    return 0


# ---- self-test -------------------------------------------------------------------------------

def _fixture():
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    return d


def _wt(d, slug, status="in-progress", age_min=0):
    import os, time
    cp = d / slug / ".scratch" / slug / "checkpoint.md"
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(f"# Checkpoint\n\nupdated: x    status: {status}\n", encoding="utf-8")
    t = time.time() - age_min * 60
    os.utime(cp, (t, t))
    return str(d / slug)


def test_cap():
    d = _fixture(); data = {}; now = 1e9
    for s in ("a", "b"):
        assert acquire(data, "r", s, _wt(d, s), 2, {"app": 8080}, now, lambda p: False)
    assert acquire(data, "r", "c", _wt(d, "c"), 2, {"app": 8080}, now, lambda p: False) is None


def test_offsets_start_at_1():
    d = _fixture(); data = {}
    got = acquire(data, "r", "a", _wt(d, "a"), 2, {"backend": 8080, "frontend": 5173}, 1e9, lambda p: False)
    assert got == {"backend": 8081, "frontend": 5174}, got


def test_reacquire_same_slug_returns_same_ports():
    d = _fixture(); data = {}; wt = _wt(d, "a")
    first = acquire(data, "r", "a", wt, 2, {"app": 8080}, 1e9, lambda p: False)
    again = acquire(data, "r", "a", wt, 2, {"app": 8080}, 1e9, lambda p: p == 8081)
    assert first == again == {"app": 8081}


def test_skips_listening_offset():
    d = _fixture(); data = {}
    got = acquire(data, "r", "a", _wt(d, "a"), 2, {"app": 8080}, 1e9, lambda p: p == 8081)
    assert got == {"app": 8082}, got


def _entry(wt, acquired):
    return {"worktree": wt, "offset": 1, "ports": {"app": 8081}, "acquired": acquired}


def test_fresh_slot_not_reclaimed_before_boot():
    import time
    d = _fixture(); now = time.time()
    e = _entry(_wt(d, "a", age_min=40), now - 10 * 60)
    assert not is_stale(e, "a", now, lambda p: False)


def test_dead_slot_reclaimed():
    import time
    d = _fixture(); now = time.time()
    e = _entry(_wt(d, "a", age_min=40), now - 40 * 60)
    assert is_stale(e, "a", now, lambda p: False)


def test_listening_slot_kept():
    import time
    d = _fixture(); now = time.time()
    e = _entry(_wt(d, "a", age_min=40), now - 40 * 60)
    assert not is_stale(e, "a", now, lambda p: p == 8081)


def test_done_or_missing_checkpoint_reclaimed():
    import time
    d = _fixture(); now = time.time()
    assert is_stale(_entry(_wt(d, "a", status="done"), now), "a", now, lambda p: False)
    wt = _wt(d, "b")
    (d / "b" / ".scratch" / "b" / "checkpoint.md").unlink()
    assert is_stale(_entry(wt, now), "b", now, lambda p: True)


def test_missing_worktree_reclaimed():
    import time
    d = _fixture(); now = time.time()
    assert is_stale(_entry(str(d / "gone"), now), "gone", now, lambda p: True)


def test_release_idempotent():
    d = _fixture(); data = {}
    acquire(data, "r", "a", _wt(d, "a"), 2, {"app": 8080}, 1e9, lambda p: False)
    release(data, "r", "a"); release(data, "r", "a")
    assert "a" not in data.get("r", {})


def test_corrupt_ledger_is_empty():
    d = _fixture(); f = d / "slots.json"
    f.write_text("{not json", encoding="utf-8")
    assert load(f) == {}
    assert load(d / "missing.json") == {}


def test_stale_lock_broken():
    import os, time
    d = _fixture(); f = d / "slots.json"
    lock = d / "slots.json.lock"
    lock.write_text("x"); t = time.time() - 60; os.utime(lock, (t, t))
    with locked(f):
        pass
    assert not lock.exists()


def test_concurrent_acquire_distinct():
    import threading, time
    d = _fixture(); f = d / "slots.json"; out = {}
    wts = {s: _wt(d, s) for s in ("a", "b")}

    def run(s):
        with locked(f):
            data = load(f)
            time.sleep(0.05)  # widen the race window
            out[s] = acquire(data, "r", s, wts[s], 2, {"app": 8080}, time.time(), lambda p: False)
            save(f, data)

    ts = [threading.Thread(target=run, args=(s,)) for s in wts]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert out["a"] != out["b"] and None not in out.values(), out


def test_listening_sees_ipv6_only_server():
    s = socket.socket(socket.AF_INET6)
    s.bind(("::1", 0)); s.listen()
    try:
        assert listening(s.getsockname()[1])
    finally:
        s.close()


def test_done_slot_kept_while_app_still_listening():
    import time
    d = _fixture(); now = time.time()
    e = _entry(_wt(d, "a", status="done"), now)
    assert not is_stale(e, "a", now, lambda p: p == 8081)


def test_offsets_distinct_across_repos():
    d = _fixture(); data = {}
    a = acquire(data, "r1", "a", _wt(d, "a"), 2, {"app": 8080}, 1e9, lambda p: False)
    b = acquire(data, "r2", "b", _wt(d, "b"), 2, {"app": 8080}, 1e9, lambda p: False)
    assert a != b, (a, b)


def test_driver_match_normalises_paths():
    d = _fixture(); wt = _wt(d, "a")
    live = {_norm(wt.replace("\\", "/").upper() if os.name == "nt" else wt): "working"}
    rows = feature_rows([wt], {}, live)
    assert rows[0]["driver"] == "working" and rows[0]["state"] == "working", rows


def test_agents_unavailable_is_unknown():
    assert drivers(["claude-does-not-exist-xyz", "agents", "--json"]) is None
    d = _fixture(); wt = _wt(d, "a")
    assert feature_rows([wt], {}, None)[0]["driver"] == "unknown"


def test_rows_done_total():
    d = _fixture(); wt = _wt(d, "a")
    cp = Path(wt) / ".scratch" / "a" / "checkpoint.md"
    cp.write_text("status: in-progress\n\n## Completed\n- T1 x\n- T2 y\n- T3 z\n\n## Next\n- not this\n",
                  encoding="utf-8")
    issues = Path(wt) / ".scratch" / "a" / "issues"; issues.mkdir()
    for i in range(5):
        (issues / f"0{i}-t.md").write_text("x")
    r = feature_rows([wt], {}, {})[0]
    assert (r["done"], r["total"]) == (3, 5), r


def test_pause_flags_non_done_only():
    d = _fixture(); a = _wt(d, "a"); b = _wt(d, "b", status="done")
    rows = feature_rows([a, b], {}, {})
    assert pause(rows) == ["a"]
    assert (Path(a) / ".scratch" / "a" / "PAUSE").exists()
    assert not (Path(b) / ".scratch" / "b" / "PAUSE").exists()
    assert feature_rows([a], {}, {})[0]["state"] == "pausing"


def test_resume_skips_live_driver():
    d = _fixture(); a = _wt(d, "a", status="paused"); b = _wt(d, "b", status="paused")
    pause(feature_rows([a, b], {}, {}))
    lines = resume(feature_rows([a, b], {}, {_norm(b): "working"}))
    assert len(lines) == 1 and "--name a " in lines[0] and "/expediter:drive-tickets a" in lines[0], lines
    assert not (Path(a) / ".scratch" / "a" / "PAUSE").exists()
    assert not (Path(b) / ".scratch" / "b" / "PAUSE").exists()


def test_status_json_shape():
    d = _fixture(); wt = _wt(d, "a")
    slots = {"a": {"worktree": wt, "offset": 1, "ports": {"app": 8081}, "acquired": 0}}
    r = feature_rows([wt], slots, {})[0]
    assert set(r) == {"slug", "worktree", "status", "driver", "state", "current", "done", "total",
                      "ports", "updated"}, set(r)
    assert r["ports"] == {"app": 8081} and r["driver"] == "stopped"
    json.dumps(r)


def test_launch_line_rejects_unsafe_slug():
    bad = {"slug": 'x"; rm -rf ~; "', "worktree": "C:/w", "status": "paused", "driver": "stopped"}
    good = {"slug": "csv-export", "worktree": "C:/w $HOME", "status": "paused", "driver": "stopped"}
    assert launch_line(bad) is None
    assert launch_line(good).startswith("cd 'C:/w $HOME' && ")


def test_pause_skips_symlinked_flag():
    d = _fixture(); a = _wt(d, "a"); target = d / "elsewhere.txt"
    try:
        (Path(a) / ".scratch" / "a" / "PAUSE").symlink_to(target)
    except OSError:
        return  # no symlink privilege on this Windows account: nothing to test
    assert pause(feature_rows([a], {}, {})) == []
    assert not target.exists()


def _self_test():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f()
        except Exception as e:
            print(f"FAIL {n}: {type(e).__name__}: {e}")
            return 1
    print(f"ok {len(tests)}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(_self_test())
    sys.exit(main(sys.argv[1:]))
