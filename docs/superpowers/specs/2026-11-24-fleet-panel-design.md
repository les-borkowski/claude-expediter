# Fleet: background drivers, status, pause and resume — design

(Supersedes the first version of this file, which built a live panel mod. Research found Claude
Code's own agent view does that job; the user confirmed `claude agents` works on their machine.)

## Intent

The user runs 2–3 expediter drivers at once via `/run-features`. They pause every driver at the end
of the workday and resume them all next morning, and want to see what each driver is doing without
hopping between tabs.

## Goals

- Drivers run as **background sessions**, so `claude agents` is the live dashboard (Working / Needs
  input / Ready for review, a summary per session, `claude attach` to answer a question).
- `/run-features status` adds what agent view can't know: tickets done / total, slot ports, and the
  driver's live state matched by worktree folder.
- **Pause right away** (user's choice), fleet-wide, at no model cost; **resume** all next morning.
- Isolation keeps working for a big Java/React project: gitignored local config reaches worktrees.

## Non-goals

- A custom panel or mod (agent view covers it).
- Killing processes the drivers didn't start; deleting worktrees or sessions (`claude rm` is never
  called — it can delete a worktree).
- Per-feature pause (whole fleet of the current repo).

## Anti-goals

- Pause loses no work. Resume never commits a half-done ticket without test + review.
- Single-session use (`/build-feature`, `/plan-feature` + `/drive-tickets` by hand) unchanged.

## Approaches considered

- **A. Background sessions + agent view + small status/pause/resume CLI (chosen).** Reuses Claude
  Code's own dashboard; expediter adds only what's specific to it.
- **B. Tabs + live panel mod (first version).** Builds a dashboard Claude Code already has.
- **C. Agent teams.** Experimental, split panes need tmux, and teammates aren't restored on resume —
  wrong for an overnight pause.

## Design

### 1. Launch (`/run-features`)

From the worktree folder (as the working directory):
`claude --bg --name <slug> --model sonnet --advisor opus "/expediter:drive-tickets <slug>"`.
It returns immediately and prints the session id; record it in the feature's checkpoint
(`session: <id>`). Fallback if `--bg` fails: the existing `wt … pwsh -NoExit -Command …` tab line.
The `wt` line stays documented for anyone who prefers tabs.

### 2. Status: `slots.py status` (+ `--json`)

Per feature (from checkpoints, as today) add: **driver** state from `claude agents --json` — the
entry whose `cwd` equals the worktree path (case-insensitive): `busy` → working, `idle` → idle,
none → stopped; plus checkpoint `blocked` → waiting on you, `paused`, `done`. Add `done/total`
(`## Completed` lines / files in `issues/`). `/run-features status` prints it.

### 3. Pause: `slots.py pause` / `/run-features pause`

`slots.py pause` writes `<worktree>/.scratch/<slug>/PAUSE` for every non-done feature of the repo
and prints what it flagged. `/run-features pause` just runs it (a user can run the script directly
for zero tokens).

The flag is enforced by a new expediter **PreToolUse hook on `Agent`** (`hooks/pause_gate.py`,
stdlib): if a `PAUSE` file exists under the session's cwd `.scratch/*/`, deny the dispatch with
"PAUSE requested — follow 'On a pause message' in /drive-tickets". A busy driver pauses at its
next dispatch. An idle driver with nothing running needs nothing: its next action would hit the gate.
A driver blocked on the user has already released its slot (escalation rule).

Driver side, `commands/drive-tickets.md` new section **On a pause message** (triggered by the
gate's denial):
1. Wait for agents already running to return; dispatch nothing new.
2. Stop the dev servers it started (its ledger ports, else the documented ports; check PID), and
   `release` any slot.
3. **WIP commit** the worktree's changes as `WIP(pause): <ticket> at <stage>` (borrowed from
   claude-squad: safe overnight, still instant).
4. Checkpoint `status: paused`; 'Current task' = ticket, fixed point (base sha), last finished stage
   (implemented / tested+reviewed with N findings / fix iteration k of 3), and the WIP sha. Then stop.

### 4. Resume: `slots.py resume` / `/run-features resume`

`slots.py resume` deletes the `PAUSE` files and prints, per feature whose checkpoint isn't done
and whose driver is stopped, the launch line from §1; `/run-features resume` runs those lines.
The new driver reads the paused checkpoint and, before anything else: `git reset --soft` the WIP
commit, then continues that ticket from the recorded stage (the dirty diff is the implementation so
far; the fix count carries over), via the build commands below. If the recorded stage doesn't match
the worktree, dispatch `verifier` (spec-check from the fixed point) to say what remains.

`/build-ticket`, `/build-ui-ticket`, `/write-docs` accept an optional brief line
"resume at stage <implemented | tested+reviewed | fix iteration k>" and skip the finished stages.
Without it, unchanged.

### 5. Small additions from the research

- **`.worktreeinclude`** (built into Claude Code): SETUP.md tells projects to list gitignored local
  files (`.env`, local Spring/React config) there so each new worktree builds first time.
- Checkpoint template: status gains `paused`; header gains `session: <id or none>`.
- Version: expediter 0.9.0. The `expediter-handoff` mod is untouched.

## Left to the builder

- Verify on this machine, with one throwaway background session, that `--bg` accepts
  `--model`, `--advisor`, `--name` and an initial slash-command prompt, and inherits PATH/env;
  if `--advisor` is refused there, drop it from the line.
- Verify the PreToolUse hook's denial text reaches the model as the tool result.
- `claude agents --json` field names as observed: `pid, cwd, kind, startedAt, sessionId, name,
  status` (`busy | idle`); treat unknown statuses as "unknown", not errors.
