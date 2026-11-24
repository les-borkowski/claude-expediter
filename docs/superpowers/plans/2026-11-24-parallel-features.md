# Parallel Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/run-features` plans several features and auto-launches a Sonnet driver tab for each; a shared slot ledger gives each feature distinct dev-server ports and caps app instances per repo.

**Architecture:** One stdlib Python script (`tools/slots.py`) owns a JSON ledger under `~/.claude/expediter/`, guarded by a lock file. Command markdown files (`/drive-tickets`, `/build-feature`, `/build-ui-ticket`) call it around dev-server start/stop; a new `/run-features` command loops plan → leave worktree → `wt` launch. No long-running agent.

**Tech Stack:** Python 3.8+ stdlib, Claude Code plugin command markdown, Windows Terminal (`wt`).

**Spec:** `docs/superpowers/specs/2026-11-24-parallel-features-design.md`

## Global Constraints

- `slots.py` is stdlib only, python 3.8+, like `hooks/*.py` and `tools/spend_report.py`.
- Ledger: `~/.claude/expediter/slots.json`; override with env `EXPEDITER_SLOTS_FILE` (tests use it).
- Lock: `O_CREAT|O_EXCL` lock file next to the ledger; break a lock older than 30 s.
- Slot = offset k ≥ 1 (0 = default ports, never assigned); every declared server gets `base + k`.
- Max instances default 2. Exit code 3 = full.
- Stale reclaim: worktree gone, checkpoint missing or `status: done`, or (no port listening AND `max(acquired, checkpoint mtime)` older than 30 min).
- Never kill a process. `status` only warns.
- Single-session use needs no new steps, flags, or config. A project without `Ports:` in `## Dev Servers` behaves exactly as today.
- Escalation (drive step 6) stops own servers and releases the slot; resume re-acquires.
- Plugin version → `0.8.0`.

## Review Focus

1. Two drivers calling `acquire` at the same moment → they get different offsets (test: `test_concurrent_acquire_distinct` in Task 1, two threads).
2. A resumed driver whose own server is still listening re-acquires → gets its **same** ports, not skipped as "in use" (`test_reacquire_same_slug_returns_same_ports`).
3. A just-acquired slot whose server is still building (nothing listening, checkpoint fresh or acquired < 30 min ago) → not reclaimed (`test_fresh_slot_not_reclaimed_before_boot`).
4. A closed tab's slot with server still listening → never auto-reclaimed; with nothing listening for 30 min → reclaimed (`test_listening_slot_kept`, `test_dead_slot_reclaimed`).
5. Missing, empty or corrupt ledger file, and a lock left by a crashed process → treated as empty / broken after 30 s, no crash (`test_corrupt_ledger_is_empty`, `test_stale_lock_broken`).

---

### Task 1: `tools/slots.py` ledger + self-test

**Files:**
- Create: `tools/slots.py`

**Interfaces:**
- Produces (CLI, used by Tasks 2–3):
  - `python3 tools/slots.py acquire <slug> --ports name=base[,name=base...] [--max N] [--worktree PATH]` → stdout one `name=port` line per server, exit 0; full → holders on stdout, exit 3. `--worktree` defaults to cwd; repo key = absolute `git -C <worktree> rev-parse --git-common-dir`, normalised with `os.path.normcase(os.path.realpath())`.
  - `python3 tools/slots.py release <slug> [--worktree PATH]` → exit 0 always.
  - `python3 tools/slots.py status [--worktree PATH]` → human-readable table, exit 0: one row per linked worktree from `git worktree list --porcelain` (slug, checkpoint status + 'Current task' line, held ports or "no slot"), then a `WARNING` line per listening port in any held-or-free offset 1..max+2 that no ledger entry accounts for. Runs stale reclaim first.
  - `python3 tools/slots.py --self-test` → runs all `test_*` functions, prints `ok N`, exit 0; non-zero on failure.
- Internal (testable, pure where possible):
  - `load(path) -> dict` / `save(path, data)`; layout `{repo: {slug: {"worktree", "offset", "ports": {name: port}, "acquired": epoch}}}`.
  - `is_stale(entry, slug, now, listening) -> bool`
  - `acquire(data, repo, slug, worktree, max_n, bases, now, listening) -> dict | None` (mutates `data`)
  - `release(data, repo, slug) -> None`
  - `listening(port) -> bool` — `socket.connect_ex(("127.0.0.1", port)) == 0`, 0.2 s timeout.
  - `locked(path)` — context manager for the lock file.

- [ ] **Step 1: Write the failing tests** in `tools/slots.py` (module-level `test_*` functions, using a temp dir and a fake `listening` set):
  - `test_cap`: max 2, three slugs → third returns `None`.
  - `test_offsets_start_at_1`: bases `{"backend":8080,"frontend":5173}` → first slug gets `{"backend":8081,"frontend":5174}`.
  - `test_reacquire_same_slug_returns_same_ports`: acquire, mark 8081 listening, acquire same slug → same dict.
  - `test_skips_listening_offset`: 8081 listening (foreign) → first slug gets 8082.
  - `test_fresh_slot_not_reclaimed_before_boot`: acquired 10 min ago, nothing listening, checkpoint in-progress → `is_stale` False.
  - `test_dead_slot_reclaimed`: acquired and checkpoint mtime 40 min ago, nothing listening → True.
  - `test_listening_slot_kept`: same as above but port listening → False.
  - `test_done_or_missing_checkpoint_reclaimed`, `test_missing_worktree_reclaimed` → True.
  - `test_release_idempotent`: release twice → no error, slug gone.
  - `test_corrupt_ledger_is_empty`: file contains `{not json` → `load` returns `{}`.
  - `test_stale_lock_broken`: lock file with mtime 60 s ago → `locked()` acquires.
  - `test_concurrent_acquire_distinct`: two threads run full CLI-path acquire (lock + load + acquire + save) against one ledger → different offsets.
- [ ] **Step 2: Run** `python3 tools/slots.py --self-test` → fails (functions undefined).
- [ ] **Step 3: Implement** the interfaces above. Checkpoint path for an entry: `<worktree>/.scratch/<slug>/checkpoint.md`; "done" = `re.search(r"status:\s*done\b", text[:600])` (same test as `hooks/resume_from_checkpoint.py`). `acquire` runs stale reclaim over the repo first; never treats the caller's own existing entry as stale.
- [ ] **Step 4: Run** `python3 tools/slots.py --self-test` → `ok 13`. Then smoke: `EXPEDITER_SLOTS_FILE=$TMP/s.json python3 tools/slots.py acquire demo --ports app=18080` → `app=18081`; `... status` lists it; `... release demo`.
- [ ] **Step 5: Commit** `feat: slot ledger for parallel feature drivers`.

### Task 2: Wire the ledger into the driving commands

**Files:**
- Modify: `commands/drive-tickets.md` (step 5 "start the app once", step 6 escalate, step 7 teardown)
- Modify: `commands/build-feature.md` (its equivalent server-startup/escalate/teardown steps — locate with grep for `Dev Servers`)
- Modify: `commands/build-ui-ticket.md` step 2
- Modify: `templates/checkpoint.md` ('Tools to have running' example row)

**Interfaces:**
- Consumes: Task 1 CLI (`acquire` / `release`, exit 3).
- Produces: a `Ports:` / `Max instances:` convention in `## Dev Servers` that Task 4 documents: `Ports: backend=8080, frontend=5173` and `{port:<name>}` placeholders in start commands/URLs.

- [ ] **Step 1:** In drive-tickets step 5, before starting servers: *if* `## Dev Servers` has a `Ports:` line, run `python3 "${CLAUDE_PLUGIN_ROOT}/tools/slots.py" acquire <slug> --ports <...> --max <Max instances or 2> --worktree <worktree>`, substitute the printed ports into commands and URLs, record ports + "slot held" in the checkpoint. Exit 3 → run non-UI frontier tickets first; when only UI tickets remain, wait with a Monitor until-loop retrying `acquire` every 3 min, noting "waiting for slot" in the checkpoint. No `Ports:` line → unchanged behaviour. A resumed driver re-runs `acquire` (same ports back).
- [ ] **Step 2:** Step 6 (escalate): stop own servers (only the ports this slug holds), `release`, checkpoint 'Next' says re-acquire and cold-start on resume. Step 7: `release` after stopping servers; the kill-by-port rule names only ledger ports for this slug.
- [ ] **Step 3:** Same three edits in `build-feature.md`.
- [ ] **Step 4:** `build-ui-ticket.md` step 2: probe/start using the ports passed in the brief when given, defaults otherwise.
- [ ] **Step 5:** Checkpoint template: add an example row `| slot <slug> (ports …) | python3 …/slots.py status | python3 …/slots.py acquire … |`.
- [ ] **Step 6: Verify** `grep -n "slots.py" commands/*.md templates/checkpoint.md` shows acquire in step 5 and release in steps 6 and 7 of both drive commands; read the diff once for a project with no `Ports:` line and confirm no instruction changed for it.
- [ ] **Step 7: Commit** `feat: drivers acquire/release dev-server slots`.

### Task 3: `/run-features` command

**Files:**
- Create: `commands/run-features.md`

**Interfaces:**
- Consumes: `/plan-feature` (invoked per plan), Task 1 `status`.
- Produces: user-facing `/run-features <plan> [<plan>...]` and `/run-features status`.

- [ ] **Step 1:** Frontmatter: `description`, `argument-hint: <plan> [<plan>...] | status`, no `model:` (runs on session model, like `/plan-feature`).
- [ ] **Step 2:** Body:
  - `status` → run `slots.py status`, print, stop.
  - Per plan, in order: run `/plan-feature <plan>` (both gates with the user; if the Skill can't be invoked, follow `plan-feature.md`'s steps); `ExitWorktree` with `keep` back to the main checkout (one line on why: plan-feature step 3 reuses an existing worktree); launch `wt -w 0 new-tab -d "<worktree>" --title "<slug>" claude --model sonnet --advisor opus "/expediter:drive-tickets <slug>"`; if `wt` isn't on PATH, print that line instead; continue to the next plan.
  - Don't read driver output; end by running `status`.
  - Stop the loop if a plan's gate is rejected; report which features launched.
- [ ] **Step 3: Verify (manual, needs the user):** run `/run-features <one tiny plan>` in a scratch repo; a new `wt` tab opens in the worktree and starts `/drive-tickets`. If `--advisor` is rejected by the CLI, drop it from the launch line here and in `plan-feature.md` step 6, and say so.
- [ ] **Step 4: Commit** `feat: /run-features launcher`.

### Task 4: Docs and version

**Files:**
- Modify: `SETUP.md` (`### ## Dev Servers` section; new `## Running several features` section after `## Checkpoints, /clear and compaction`)
- Modify: `README.md` (command table, "shape of it" diagram, intro command count "Seven commands" → "Eight commands")
- Modify: `.claude-plugin/plugin.json` version `0.7.0` → `0.8.0`

- [ ] **Step 1:** SETUP `## Dev Servers`: document `Ports:` (`name=base`, `{port:name}` placeholders, offset 0 = defaults left for manual runs) and `Max instances:` (default 2), both optional.
- [ ] **Step 2:** SETUP `## Running several features`: `/run-features`, the ledger location, `status`, reclaim rule (30 min, never kills), escalation releases the slot, single-session use unchanged.
- [ ] **Step 3:** README table row + diagram line; version bump.
- [ ] **Step 4: Verify** via `/write-docs`-style fact-check: every claim matches Tasks 1–3 (dispatch `expediter:docs-fact-checker` on the diff).
- [ ] **Step 5: Commit** `docs: parallel features`.
