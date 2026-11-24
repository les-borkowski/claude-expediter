#!/usr/bin/env python3
"""Dev-server slot ledger shared by parallel expediter drivers. Stdlib only, python 3.8+.

  slots.py acquire <slug> --ports name=base[,name=base...] [--max N] [--worktree PATH]
  slots.py release <slug> [--worktree PATH]
  slots.py status [--worktree PATH]
  slots.py --self-test
"""
import argparse, contextlib, json, os, re, socket, subprocess, sys, time
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
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


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
    if re.search(r"status:\s*done\b", text[:600]):
        return True
    if any(listening(p) for p in entry["ports"].values()):
        return False
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
    held = {e["offset"] for e in slots.values()}
    k = 1
    while k in held or any(listening(b + k) for b in bases.values()):
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


def _status(data, repo, worktree, now):
    reclaim(data, repo, now, listening)
    slots = data.get(repo, {})
    print(f"repo: {repo}")
    wts = [l[9:] for l in _git(worktree, "worktree", "list", "--porcelain").splitlines()
           if l.startswith("worktree ")]
    for wt in wts:
        for cp in sorted(Path(wt).glob(".scratch/*/checkpoint.md")):
            slug = cp.parent.name
            text = cp.read_text(encoding="utf-8", errors="ignore")
            st = re.search(r"status:\s*(\S+)", text[:600])
            cur = re.search(r"## Current task\s*\n+(.+)", text)
            held = slots.get(slug)
            ports = ", ".join(f"{n}={p}" for n, p in held["ports"].items()) if held else "no slot"
            print(f"  {slug:<28} {st.group(1) if st else '?':<12} {ports:<30} "
                  f"{cur.group(1).strip()[:60] if cur else ''}")
    if not wts:
        print("  (no worktrees)")
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
    s = sub.add_parser("status")
    for p in (a, r, s):
        p.add_argument("--worktree", default=os.getcwd())
    args = ap.parse_args(argv)

    wt = os.path.realpath(args.worktree)
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
            _status(data, repo, wt, now)
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
    assert is_stale(_entry(_wt(d, "a", status="done"), now), "a", now, lambda p: True)
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
