---
description: Drive an approved feature's tickets to a reviewable branch on a cheaper model — reads the handoff from /plan-feature, runs each ticket through its build command, commits per ticket. Never merges.
argument-hint: <feature-slug>
model: sonnet
---

Drive the approved tickets for feature `$ARGUMENTS` to a reviewable branch.

This is the **driving half** of `/build-feature`. Planning already happened in a `/plan-feature` session; this session sequences the work. It's meant to run on Sonnet — the `model: sonnet` above forces that for the batch even if the session was started on something heavier, but starting the session on Sonnet is better (no model switch, no discarded cache). Best of all is `claude --model sonnet --advisor opus` from the worktree: Sonnet sequences, and Opus is consulted only at the few points where judgement matters.

**First, load the handoff.** Read `.scratch/$ARGUMENTS/handoff.md` and list `.scratch/$ARGUMENTS/issues/`. If either is missing, stop and tell the user to run `/plan-feature` first. `cd` to the worktree path the handoff names and confirm with `git branch --show-current` that you're on the feature branch. Everything below uses the build/test commands and flags from the handoff — do not re-derive them.

**Keep a live checkpoint.** Before the first ticket, write `.scratch/$ARGUMENTS/checkpoint.md` from the template at `${CLAUDE_PLUGIN_ROOT}/templates/checkpoint.md` (goal from the handoff, `handoff:` and `worktree:` filled in). Update it after every ticket commit (step 5), whenever you start or restart a dev server, and whenever you stop to escalate. It is what the expediter SessionStart hook re-injects after `/clear` or a compaction, so a batch interrupted mid-feature resumes exactly where it stood. If you find a checkpoint already present and not `status: done`, you are resuming: read it, check its 'Tools to have running', and continue from its 'Next' instead of starting from the first ticket.

**Framing rules (same discipline as build-ticket):**
- You (the orchestrator) do NOT edit code yourself. Every code change flows through `/build-ticket`'s subagents so each stays scoped to its role. You only write plan/ticket artifacts, create the branch, and commit.
- Each ticket brief you pass to `/build-ticket` is a self-contained contract. Do NOT tell it or its subagents to "read the plan file" — inline the specifics (goal, files, approach, exact verify criteria).
- The backend agents (`feature-implementer`, `test-writer`, `code-reviewer`) declare narrow tool allowlists, so they have `Bash` but no `PowerShell` and no MCP tools — a property of those definitions, not a platform limit (`frontend-dev` inherits both). Give them Bash-syntax build commands.
- **Use the build and test commands from the handoff.** They were resolved and verified during planning. Only if one fails as not-found (a toolchain bumped since), re-resolve it from `## Build & Test Commands` in `CLAUDE.md`, and note the change in your final report.
- **Don't do lookups yourself.** Writing a self-contained ticket brief needs exact file paths and call sites. Dispatch `quick-lookup` (haiku, read-only) for those instead of grepping in your own context — over a whole feature's worth of tickets that adds up, and this orchestrator's context is the one you most want to keep clean.
- Inside this command the recipe governs. Superpowers skills are used at the named integration points below; their own triggers do not restructure the loop. Skip any integration point whose skill isn't installed.


**Keep this context small.** You're a sequencer. Read verdicts, not diffs; read `verifier` output, not reviewer transcripts. Don't paste agent reports back into your own reasoning at length — note status, files, test result, open findings, docs impact, and move on.

**Use the advisor at decision points, if one is on.** If an advisor tool is in your tool list (the session was started with `--advisor opus`, or `/advisor` is set), consult it at these moments and no others: (a) when a ticket's fix loop reaches its second failed iteration, before spending the third; (b) when a `verifier` verdict and your own reading of the ticket disagree; (c) once before the final report, to check the branch against the plan. Each call reads this whole conversation at Opus rates, so don't consult it for routine sequencing — and keep the checkpoint current so a `/clear` keeps these calls cheap. If no advisor is on, skip all of this.

**Pacing:** the approval gates already happened in `/plan-feature`. Run tickets straight through in auto/batch mode. Only stop on unresolved findings after 3 fix iterations, or a genuine blocker.

**Steps:**

5. **Drive tickets (auto/batch).**

   **Before the first ticket: if any ticket in the plan is UI-facing, start the app once, here.** Browser verification needs a running app, and starting it is the most expensive thing in the frontend cycle — a cold backend that loads a large production dataset can spend minutes doing it. Starting once per *feature* instead of once per *ticket* pays that cost a single time.
   - Use the commands in the project's `## Dev Servers` section, preferring its lightweight/fixture-backed mode. Run them in the background from the worktree checkout, and note the URLs.
   - Do **not** use a skip-the-build startup flag for this first start: where a project has one, its modules resolve from a shared local artifact cache, and a stale artifact there boots normally while silently serving old code. A worktree's cache holds whatever branch last built, so the first full build in a new worktree is mandatory.
   - `/build-ui-ticket` will find the servers already reachable and skip its own startup step. Leave them running across tickets, and tear them down only at step 7.
   - **A ticket that changes server-side code invalidates the running server.** After committing such a ticket, restart it before the next UI-facing ticket, or the browser check will exercise stale code.

   Work the dependency **frontier** — any ticket whose blockers are all committed (a linear chain runs top to bottom). For each ticket:
   - Note the current `HEAD` as this ticket's **fixed point** (base commit).
   - Build a self-contained brief inline from the ticket file plus the refined-plan context: goal, exact file list, approach, and exact verify criteria. Carry the ticket's flags from `handoff.md` (TDD, opus-reviewer, complex) into the brief.
   - **Route by ticket shape:** run `/build-ticket <brief>` for non-UI tickets, `/build-ui-ticket <brief>` when the acceptance criteria are visual or interaction-based (it dispatches `frontend-dev`, which verifies in a real browser inside the implementer), or `/write-docs <brief>` for a docs-only ticket — one marked `Type: docs`, or whose entire deliverable is prose in the documentation surfaces. Do not send a docs ticket through the dev loops: their test and build steps have nothing to do, and `code-reviewer`'s checklist is entirely code conventions. For a full-stack ticket, it should have been split during `/plan-feature`; if it stays whole, run the backend slice through `/build-ticket` first, then the UI slice through `/build-ui-ticket`. Either way, wait for it to return.
   - **Complexity escalation** — if the ticket is complex (crosses backend + frontend, adds a new module / interface / screen, touches many files, or is flagged complex in the handoff), after the cycle returns clean dispatch `verifier` in **spec-check** mode with the fixed point (this ticket's base commit) and the ticket file path. It reads the diff and the spec so you don't; you get back a compact verdict. Send any confirmed gaps back through the build command (respect its 3-iteration bound). If the ticket is flagged for an Opus review, dispatch `code-reviewer` with `model: opus` for this pass instead. This escalation is for **code** tickets; a docs ticket's equivalent is `/write-docs`'s own fact-check plus its stale-reference sweep.
   - On a clean result, **commit** the ticket's changes onto `feature/<slug>` with a message referencing the ticket number/title. If a background security or review hook rewakes you with findings, address or acknowledge them before advancing. Then advance to the next frontier ticket without pausing.
   - **Update the checkpoint.** Move the ticket to 'Completed' (title, sha, test count, review status), set 'Current task' and 'Next' to the following frontier ticket, and refresh 'Tools to have running' with what's actually up. Keep it a snapshot, not a log.
   - **Record the docs impact.** After the commit, append one line to `.scratch/<feature-slug>/docs-impact.md` naming what this ticket changed that a living overview, a `CLAUDE.md`, or a README will need to reflect — or "none". The build commands report this in their handback; just carry it across. This is a durable artifact on purpose: a docs sweep late in a long feature must not depend on your context surviving compaction, and `/write-docs` step 1 reads it to scope the sweep.

6. **Escalate, don't spin.** Stop and report to the user only when a ticket's findings remain after 3 fix iterations, or a genuine blocker appears (ambiguous requirement, failing infrastructure). Otherwise run to completion.

7. **Final report — do NOT merge.** Set the checkpoint to `status: done` first, so a later `/clear` doesn't resurrect finished work.
   Summarise: the branch name, the worktree path, each ticket completed with its test result and final review status, and any escalations. Then use `superpowers:finishing-a-development-branch` to present the structured completion options (merge locally / push + PR / keep the branch / discard) — but never merge or push without the user choosing it. Once the user has chosen, use `ExitWorktree` to leave the worktree: `keep` if they want to keep iterating there or review it further, `remove` once it's been merged/pushed or they discard it.
   - **Stop the dev servers you started in step 5** before removing a worktree. Note that stopping a background build-tool task does not necessarily kill the process it forked — a forked server keeps its port bound and may hold a database or lock file open, so the next boot fails. Find the PID by port and kill it explicitly, checking first that it isn't another session's server.
