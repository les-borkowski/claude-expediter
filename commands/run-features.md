---
description: Plan several features one after another, and launch a Sonnet driver for each in its own Windows Terminal tab as soon as its plan is approved. `/run-features status` shows every feature's progress and dev-server slot. Never writes code.
argument-hint: <plan> [<plan>...] | status
---

Run these features in parallel: $ARGUMENTS

You are the **manager**: you plan each feature with the user, launch its driver, and move on. You never drive tickets and never read a driver's output — each driver is its own session, and the shared slot ledger (`${CLAUDE_PLUGIN_ROOT}/tools/slots.py`) keeps their dev servers apart, so nothing needs watching.

**If the argument is `status`:** run `python3 "${CLAUDE_PLUGIN_ROOT}/tools/slots.py" status` from the main checkout, print its output as-is, and stop. Point out any `WARNING` line: an app copy no feature accounts for, still using RAM. Never kill it yourself — say which port, and let the user decide.

**Otherwise, for each plan in the order given:**

1. **Plan it.** Run `/expediter:plan-feature <plan>`, or if it can't be invoked, follow `${CLAUDE_PLUGIN_ROOT}/commands/plan-feature.md` steps 1–5. Both approval gates stay with the user. Skip its step 6 hand-off block: you launch the driver yourself below. If the user rejects or abandons this plan, skip to the next one.
2. **Leave its worktree.** `ExitWorktree` with action `keep`, back to the main checkout. This is required: `/plan-feature` step 3 reuses whatever worktree the session is in, so the next plan would otherwise land in this feature's worktree.
3. **Launch the driver** in a new Windows Terminal tab:

   ```
   wt -w 0 new-tab -d "<absolute worktree path>" --title "<slug>" claude --model sonnet --advisor opus "/expediter:drive-tickets <slug>"
   ```

   If `wt` isn't on PATH (not Windows, or Windows Terminal not installed), don't launch anything — print that `claude ...` line with the worktree path for the user to run, and carry on.
4. Go straight to the next plan; the driver runs on its own.

**When all plans are done:** report one line per plan — slug, worktree, launched / printed / skipped — then run the `status` step above so the user sees the starting picture. Remind them that `/run-features status` refreshes it at any time, and that each driver tab stops on its own to ask when it needs them.
