---
description: Plan several features one after another and launch a Sonnet driver for each as a background session as soon as its plan is approved. `status` shows every feature's state, progress and ports; `pause` stops every driver at once for the night; `resume` restarts them. Never writes code.
argument-hint: <plan> [<plan>...] | status | pause | resume
---

Run these features in parallel: $ARGUMENTS

You are the **manager**: you plan each feature with the user, launch its driver, and move on. You never drive tickets and never read a driver's output. Each driver is a Claude Code **background session**: `claude agents` is the user's live dashboard for them (working / needs input / done, a summary per session), and `claude attach <slug>` opens one to answer a question. The shared slot ledger (`${CLAUDE_PLUGIN_ROOT}/tools/slots.py`) keeps their dev servers apart.

Run every `slots.py` command below from the main checkout as `python3 "${CLAUDE_PLUGIN_ROOT}/tools/slots.py" <cmd>`.

**`status`:** run `slots.py status`, print its output as-is, and stop. Each row: feature, state (working / idle / waiting on you / pausing / paused / stopped / done), tickets done/total, ports, current task. Point out any `WARNING` line: an app copy no feature accounts for, still using RAM. Never kill it yourself — say which port, and let the user decide.

**`pause`:** run `slots.py pause` and print what it flagged. It writes a `PAUSE` flag into every unfinished feature; expediter's pause hook then refuses each driver's next agent dispatch and sends it through its pause steps (stop its app, free its slot, WIP-commit, checkpoint `paused`). Tell the user to watch `/run-features status` until every row reads `paused` (an idle or waiting driver may need `claude attach <slug>` and any message to take its next step), then they can stop for the day. Nothing else to do.

**`resume`:** run `slots.py resume`. It clears the flags and prints one launch line per unfinished feature whose driver is no longer running. Run each printed line as-is (Bash), then run `status`. A driver whose session is still alive just continues on its own once its flag is gone; if one sits idle, tell the user to `claude attach <slug>` and say "resume".

**Otherwise, for each plan in the order given:**

1. **Plan it.** Run `/expediter:plan-feature <plan>`, or if it can't be invoked, follow `${CLAUDE_PLUGIN_ROOT}/commands/plan-feature.md` steps 1–5. The design gate (step 2) stays with the user; the **ticket-breakdown gate is waived**: tell `/to-tickets` the breakdown is pre-approved, so it checks granularity and blocking edges itself, prints the list, and writes the ticket files without asking. Skip its step 6 hand-off block: you launch the driver yourself below. If the user rejects or abandons this plan, skip to the next one.
2. **Leave its worktree.** `ExitWorktree` with action `keep`, back to the main checkout. This is required: `/plan-feature` step 3 reuses whatever worktree the session is in, so the next plan would otherwise land in this feature's worktree.
3. **Launch the driver** as a background session, from the worktree (Bash):

   ```
   cd "<absolute worktree path>" && claude --bg --name <slug> --model sonnet --advisor opus "/expediter:drive-tickets <slug>"
   ```

   It returns at once and prints `backgrounded · <id> · <slug>`. Write `session: <id>` into the feature's checkpoint header. A background session refuses a folder Claude hasn't been trusted in ("Workspace not trusted"); worktrees under the repo's `.claude/worktrees/` inherit the repo's trust. If it fails for that or any other reason, fall back to a Windows Terminal tab:

   ```
   wt -w 0 new-tab -d "<absolute worktree path>" --title "<slug>" pwsh -NoExit -Command "claude --model sonnet --advisor opus '/expediter:drive-tickets <slug>'"
   ```

   (PowerShell 7 with the user's profile; keep the quoting exactly, and no `;` — `wt` treats it as a separator. No `wt` either: print the `claude …` line for the user.)
4. Go straight to the next plan; the driver runs on its own.

**When all plans are done:** report one line per plan — slug, worktree, background / tab / printed / skipped — then run `status`. Remind the user: `claude agents` is the live view, `claude attach <slug>` answers a driver, and `/run-features pause` / `resume` handle the end of the day.
