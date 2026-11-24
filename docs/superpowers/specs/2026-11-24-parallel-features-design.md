# Parallel features: `/run-features` + slot ledger — design

## Intent

The user runs 2–3 expediter features at once, each in its own terminal (token savings from the
Sonnet driver leave room under the usage limit). Today each one is launched and handed off by hand:
run `/plan-feature`, read the handoff block, open a terminal in the worktree, start
`claude --model sonnet --advisor opus`, type `/drive-tickets <slug>`. That is the tedious part.

The second problem is shared machine resources. Each UI feature starts its own copy of the app
(e.g. gdi-cleanse-tool); too many copies exhaust RAM, and two copies on the default port collide.
Nothing today coordinates ports or caps instances across sessions.

## Goals

- One command, run in one (Opus) terminal, takes several plans, plans each in turn with the user,
  and launches a Sonnet driver for each in its own Windows Terminal tab — no manual handoff.
- A shared ledger hands each feature a distinct port and caps how many app instances run at once,
  per repo. A driver that can't get a slot waits rather than overloading the machine.
- A one-shot status view: each running feature's checkpoint state and the slots it holds.

## Non-goals

- Splitting one feature's tickets across parallel sessions (features are the unit of parallelism).
- Headless/background drivers (`claude -p`). Drivers stay interactive so they can escalate.
- A long-running manager agent. Tracking is a deterministic script; nothing polls on tokens.
- Non-Windows launching. Off Windows (or without `wt`), the command prints the launch line instead.
- Changing `/build-feature` (single-session path) beyond what the slot rules require.

## Anti-goals

- The manager session's context must not grow with driver activity — it never reads driver output.
- A crashed/closed driver must not hold a slot forever and deadlock the others.
- Running a single session must stay as easy as today (user requirement): `/build-feature`, and
  `/plan-feature` + `/drive-tickets` by hand, need no new steps, flags, or config. `/run-features`
  with one plan is also valid (plan, then auto-launch the driver tab).
- Existing single-feature use (`/plan-feature` + `/drive-tickets` by hand) keeps working. A project
  with no port config behaves exactly as today; one with port config uses the ledger whenever a
  driver starts servers, however it was launched (so a hand-run driver still counts toward the cap).

## Approaches considered

- **A. Manager command + lock script (chosen).** `/run-features` plans and launches; a stdlib
  Python script owns a file ledger of ports/slots. Drivers stay interactive; tracking costs no tokens.
- **B. Headless drivers via `claude -p`.** Fewer windows and exit notifications, but drivers can't
  ask the user anything and permission prompts block or fail. Rejected: too fragile on a large project.
- **C. Long-running manager agent.** Matches the "manager" picture literally, but burns tokens to
  watch, and drivers must be real sessions anyway (subagents can't spawn subagents, and
  `/drive-tickets` dispatches agents). Rejected: A's script does the same job deterministically.

## Design

### 1. `tools/slots.py` (stdlib only, python 3.8+)

Ledger at `~/.claude/expediter/slots.json`, shared by every session on the machine. Writes are
guarded by an exclusive lock file (`os.open(..., O_CREAT|O_EXCL)`, retry with short backoff, break
a lock older than 30 s).

Each entry: `repo` (the git common dir, so all worktrees of one repo count together), `slug`,
`worktree`, `offset`, `ports` (name → port), `acquired` timestamp.

**A slot is an offset, not a single port** (my call — covers apps with a backend and a frontend dev
server). The project declares one base port per server (§2); slot offset `k` gives every server
`base + k`. Offsets are 1, 2, 3… (offset 0 = the default ports, left free for the user's own
manual runs).

Subcommands:

- `acquire <slug> --worktree <path> --max <N> --ports name=base[,name=base...]` — reclaims stale
  entries (below), then if the repo holds fewer than N entries, picks the lowest offset that the
  ledger doesn't hold **and** where none of that offset's ports is listening, records it, and prints
  `name=port` lines. If the slug already holds a slot, prints its existing ports (idempotent —
  resume-safe). If full, prints the holders and exits 3.
- `release <slug>` — removes the slug's entry. Idempotent.
- `status` — for the repo of the current directory (my call): every linked worktree from
  `git worktree list` with its `.scratch/*/checkpoint.md` status and current task, the slot it
  holds if any, and a **warning** for anything listening on a port in a slot range that the ledger
  doesn't account for (an orphaned server still using RAM). It never kills anything — killing
  another session's process is the user's decision.
- **Stale reclaim** (run inside `acquire` and `status`), my call: drop an entry when its worktree no
  longer exists, or its checkpoint is missing or `status: done`, **or** none of its ports is
  listening and its checkpoint hasn't been updated for 30 minutes. That last rule is the liveness
  signal: a closed tab's server dies or goes quiet and the slot frees within ~30 min instead of the
  24 h checkpoint max-age. The 30-min grace covers the first build/boot after `acquire`.
  Reclaiming an entry whose server is still listening never happens automatically — `status` shows
  it, `release <slug>` frees it.

Ships with a small assert-based self-test (`python tools/slots.py --self-test`) covering cap,
idempotent re-acquire, port skipping, and stale reclaim, against a temp ledger path
(`EXPEDITER_SLOTS_FILE` env override).

### 2. Project config: `## Dev Servers` gains two lines (SETUP.md documents them)

- **Ports:** one `name=base` per server, with `{port:name}` placeholders in the start commands and
  URLs (e.g. a frontend command passing `{port:backend}` as its proxy target).
- **Max instances:** how many copies may run at once on this machine (default 2 if absent).

If a project doesn't declare ports, drivers behave as today (no ledger) and `status` notes it.
`/build-feature` follows the same rule as `/drive-tickets` (it shares the step-5 server startup).
`slots.py` hard-codes nothing from plugin options; callers pass what they need as arguments.

### 3. `/drive-tickets` and `/build-ui-ticket` changes

- Before starting dev servers (drive-tickets step 5), `acquire` a slot with the project's max and
  base ports; substitute the ports into the start commands and the app URLs; record the ports and
  "slot held" in the checkpoint's 'Tools to have running'. A resumed driver re-runs `acquire`
  (idempotent) and gets the same ports back.
- Full (exit 3): run any non-UI frontier tickets first; when only UI tickets remain, wait with a
  Monitor until-loop retrying `acquire` (every few minutes), and say so in the checkpoint.
- **Escalation gives the slot up (user's decision).** When a driver stops to ask the user (step 6),
  it stops its dev servers (by its own ledger ports only), runs `release`, and notes in the
  checkpoint that servers must be restarted. On the user's answer it re-`acquire`s (possibly waiting)
  and cold-starts. Rationale: a waiting user can take hours; other features' UI tickets and RAM
  matter more than a few minutes of restart.
- `release` at step 7 after stopping the servers.
- `/build-ui-ticket` uses the port passed in by the caller rather than the default one when probing
  and starting; its existing "non-default port → verify a branch-only endpoint" rule applies.
- Killing a server by port (step 7) only kills the port this slug holds in the ledger.

### 4. `/run-features <plan> [<plan>...]` and `/run-features status`

- `status` → runs `slots.py status` and prints it. Nothing else.
- Otherwise, for each plan in order:
  1. Run the `/plan-feature` steps for it (both approval gates stay with the user).
  2. **`ExitWorktree` (keep)** back to the main checkout. Required: `/plan-feature` step 3 skips
     worktree creation when already inside one, so the next plan would otherwise reuse this
     feature's worktree.
  3. Launch the driver: `wt -w 0 new-tab -d <worktree> --title <slug> claude --model sonnet
     --advisor opus "/expediter:drive-tickets <slug>"`. If `wt` isn't available, print that line
     for the user to run.
  4. Move on to the next plan while that driver runs.
- Ends with the `status` output. The manager does not monitor drivers afterwards; the user re-runs
  `/run-features status` when they want a view.
- Runs on the session's model (intended: Opus), like `/plan-feature`.

### 5. Docs

README command table + "shape of it" diagram, SETUP.md `## Dev Servers` additions and a short
"Running several features" section, plugin version bump to 0.8.0.

## Left to the builder

- Exact lock-retry/backoff numbers, ledger JSON layout, output formatting of `status`.
- Whether `/run-features` invokes `/plan-feature` or inlines its steps (prefer invoking, to avoid
  two copies of the planning recipe drifting).
- Port-in-use detection method (a `socket.connect_ex` probe on localhost is enough).
