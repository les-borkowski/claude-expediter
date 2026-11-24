# Fleet panel, pause and resume — design

## Intent

The user runs 2–3 expediter drivers at once via `/run-features`, each in its own Windows Terminal
tab. They pause every driver at the end of the workday and resume them all next morning. With an
agent launching the drivers, that's tab-hopping: no single view of what each is doing, and no one
switch to stop or restart them all. They want a live view **in the manager's terminal** and a
fleet-wide pause/resume.

## Goals

- A live side panel in the manager session: one row per feature — driver state, current ticket,
  tickets done / total, slot ports — refreshing on its own, costing no model tokens.
- `pause`: every live driver stops **right away** (user's choice): waits only for agents already
  running, leaves half-done work uncommitted in its worktree, stops its app, frees its slot,
  checkpoints `status: paused`.
- `resume`: reopens a pwsh tab (same launch line as `/run-features`) for every feature whose
  checkpoint is `paused`, or not done with no live driver; each continues from its checkpoint,
  including working out where a half-done ticket stood.

## Non-goals

- Killing sessions or processes. Pause is a message; the user closes the tabs once rows read paused.
- Per-feature pause from the panel (pause/resume act on the whole fleet of the current repo).
- Anything outside the current repo's worktrees.
- Non-terminal surfaces (desktop/VS Code) — the panel may render there, but isn't designed for them.

## Anti-goals

- Pause must not lose work: uncommitted changes stay in the worktree and the checkpoint says exactly
  which ticket, which stage finished, and which files are dirty.
- A resumed half-done ticket must not be committed without passing test + review.
- Single-session use stays unchanged; the mod is inert in a session that never opens the panel.

## Approaches considered

- **A. Live panel mod (chosen).** Mod pane, timer refresh, zero tokens per refresh.
- **B. `/run-features status` table on demand.** No live view; each look costs a manager turn.
- **C. Status-line summary + B.** Lightest, but detail still on demand.

## Design

### 1. Where it lives (my call)

Inside the existing `expediter-handoff` mod (`mods/expediter-handoff/`), not a new mod: it's
already installed from the user's marketplace alongside expediter, so nothing new to install or
register in the marketplace repo. Version bump to 0.3.0.

### 2. Data: `slots.py status --json`

Add `--json` to `status`: `{"repo", "features": [{"slug", "worktree", "status", "current",
"done", "total", "ports" | null, "updated"}], "warnings": [str]}`. `done` = lines under
`## Completed` starting with `- `; `total` = files in `<worktree>/.scratch/<slug>/issues/`. Text
output unchanged. Self-test covers the JSON shape.

The mod finds `slots.py` through the installed expediter plugin's path (from
`~/.claude/plugins/installed_plugins.json`, entry `expediter@*`); if not found, the panel shows one
line saying so. (Builder verifies the file and its shape on this build.)

### 3. The panel

- Opened by a mod slash command `/fleet` (toggle), and automatically when a prompt starting with
  `/expediter:run-features` is submitted.
- Refreshes every 5 s (`$.clock.every`): runs `slots.py status --json` from the session cwd, and
  calls the `ListAgents` tool through `$.tool.call` to see which sessions are live and their state.
  A driver session is matched to a feature by its name starting with the worktree folder's name
  (session names derive from the cwd folder, e.g. `feature-csv-export-3a`).
- Row state, first match wins:
  - checkpoint `done` → **done**
  - checkpoint `paused` → **paused**
  - `PAUSE` file present → **pausing**
  - checkpoint `blocked` → **waiting on you** (whether or not its tab is open)
  - no live session → **closed** (needs resume)
  - live session busy → **working**; idle → **idle**
- Columns: feature, state, current task (truncated), done/total, ports or `—`. Footer: the
  status `warnings` (orphaned app copies) and the last refresh time.

### 4. Pause and resume — mod commands, no model turns

- `/fleet pause` → two signals, because a busy driver's whole feature can be one long turn and a
  peer message may only land at its next turn boundary (my call):
  1. writes a flag file `<worktree>/.scratch/<slug>/PAUSE` for every non-done feature of this repo;
  2. `$.session.send` to every live driver session:
     `"expediter: PAUSE — follow the 'On a pause message' section of /drive-tickets."`
  The same mod runs in the driver sessions (it's a user-scope install), and there a `tool.call` hook
  on `Agent` checks for its feature's `PAUSE` file (feature = the `.scratch/*/` under the session's
  cwd) and **denies the dispatch** with the reason "PAUSE requested — follow 'On a pause message'
  in /drive-tickets". So a busy driver pauses at its very next agent dispatch, an idle one on the
  message. Rows show **pausing** while a `PAUSE` file exists and the checkpoint isn't `paused` yet.
  Resume deletes the `PAUSE` files first.
- `/fleet resume` → for each feature row in **paused**, **closed**, or **waiting on you** with no
  live session (a relaunched blocked driver simply asks its question again in the new tab), spawn the
  `/run-features` launch line (`wt -w 0 new-tab -d … pwsh -NoExit -Command "claude … '/expediter:drive-tickets <slug>'"`)
  via `$.process.spawn`. A paused row whose session is still open gets a message
  `"expediter: RESUME — continue from your checkpoint."` instead of a new tab.

### 5. Driver side (`commands/drive-tickets.md`)

New section **On a pause message**:
1. Dispatch nothing new. Wait for agents already running to return; note their results.
2. Do not commit. Stop the dev servers this driver started — its ledger ports when it holds a
   slot, else the documented ports, checking the PID is its own — and `release` any slot. Stopping
   them is the point of pausing overnight (RAM), slot or not.
3. Write the checkpoint with `status: paused`: 'Current task' = ticket, its fixed point (base sha),
   the last stage that finished (implemented / tests written / review returned with N findings /
   fix iteration k of 3), and `git status --short` of the worktree. 'Next' = "resume: re-acquire
   slot, restart servers, continue <ticket> from <stage>".
4. Reply `paused` and stop.

On resume (checkpoint `paused`), before the normal resume path: if the worktree is dirty for the
recorded ticket, continue that ticket's cycle from the recorded stage, with the dirty diff as the
implementation so far; the fix-loop count carries over. Never commit it without the normal test +
review gate. If the recorded stage doesn't match what's in the worktree, dispatch `verifier`
(spec-check, from the fixed point) to say what remains, then continue.

**The build commands change too** (my call — they own the stages and the 3-iteration bound):
`/build-ticket`, `/build-ui-ticket` and `/write-docs` accept a brief that says "resume at stage
<implemented | tested+reviewed | fix iteration k>", skip the stages already done, and start the fix
loop at k. Without that line they behave exactly as today.

Every launched feature has a checkpoint before its driver starts (`/plan-feature` step 5 writes it),
so rows come from checkpoints alone; a worktree with no checkpoint gets no row.

`templates/checkpoint.md` status line gains `paused`. The resume hooks already treat any non-done
status as live — unchanged.

## Left to the builder

- Exact pane layout, colours, truncation; refresh interval within 3–10 s.
- How `ListAgents` output is parsed (verify its text shape on this build) and whether a session
  name reliably starts with the worktree folder name; if not, fall back to checkpoint mtime
  (< 2 min → working) and say so in the panel.
- Whether a peer message reaches a busy driver mid-turn or only at its next turn boundary — verify,
  and document the expected pause latency in SETUP.md.
