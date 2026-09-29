---
description: Run one documentation task through write -> fact-check -> stale-ref sweep with a bounded auto-fix loop (max 3), then hand results back without auto-advancing.
argument-hint: <self-contained docs task brief>
model: sonnet
---

Run this single, self-contained documentation task through the docs subagent cycle with a bounded fix-loop: $ARGUMENTS

This is the documentation sibling of `/build-ticket`. Same contract: it executes ONE unit of work and returns to you at the end — it does NOT advance to the next task. The caller owns sequencing and pausing for go-ahead.

**What makes this different from `/build-ticket`:** there is **no test step and no build step** — documentation has neither. Verification is fact-checking prose against the code it claims to describe, plus a stale-reference sweep. The dev loops exist to make code work; this loop exists to make the written record *true*. Use it for docs-only tickets, documentation sweeps, and any ticket whose whole deliverable is prose.

**Rules for the whole cycle:**
- You (the orchestrator running this command) do NOT edit docs yourself. Every change goes through `docs-writer` so the author and the checker stay separate — the author grading its own factual accuracy is the failure mode documentation already has.
- The task brief above is the contract. Do NOT tell subagents to "read the plan file" — pass them the specifics inline (which docs, which code facts, the exact allow-list and do-not-touch list).
- Give agents an explicit file list and the actual `git diff` of the code being documented, never "look at the changes."
- **Nothing here touches source or config.** If accurate documentation would require a code change, that is a dev ticket: report it to the caller and leave the code alone.
- `docs-writer` and `docs-fact-checker` declare narrow tool allowlists — `Bash` but no `PowerShell` and no MCP tools. Give them Bash-syntax commands. Neither can drive a browser; HTML overviews are checked by reading, not rendering.
- **Audience: developers plus the product/project management team.** Prose is brief, professional, and to the point — technical where it needs to be, but acronyms and internal terms get expanded on first use. State this in the brief; `docs-writer` carries the full rule.
- Inside this command the recipe governs. Superpowers skills are used at the named integration points below; their own triggers do not restructure the loop. Skip any integration point whose skill isn't installed.

**Steps:**

0. **Isolate (standalone runs only).** Skip this step when nested inside `/drive-tickets` or `/build-feature` (it already sets up an isolated worktree per `superpowers:using-git-worktrees`, and this cycle inherits that session's working directory) or when the session is already in a linked worktree. Otherwise, follow `superpowers:using-git-worktrees` Step 0 (detect existing isolation), then use the native `EnterWorktree` tool before Step 1 — do not drop to raw `git worktree add` while the native tool is available. If isolating, every file path given to subagents below must point at the worktree's checkout, not the original checkout.

1. **Scope the docs surface (orchestrator).** Decide *before* dispatching which files may change. Read the project's `## Documentation Map` (in `CLAUDE.md` or `docs/CLAUDE.md`) and build two explicit lists:
   - **Allow-list** — the specific doc files this ticket may edit, drawn from the brief plus the code being documented plus any accumulated docs-impact notes (`.scratch/<feature-slug>/docs-impact.md`, if `/build-feature` has been writing one). Candidates: the project's living overviews, its `CLAUDE.md` files, its module READMEs, and `.claude/agents/*.md` + `.claude/commands/*.md`.
   - **Do-not-touch list** — every frozen/historical doc directory (plans, design records), all source, all config.

   Also gather the **code facts**: the relevant `git diff <fixed-point>...HEAD` and the paths/symbols the docs must describe. Both lists and the facts go inline into the brief.

2. **Write** — dispatch `docs-writer` with the task brief, the allow-list, the do-not-touch list, and the code facts from step 1. Wait for it; note the exact files it changed and which claims it reported verifying where. If it refused part of the brief (an edit to a frozen plan, or a doc that can't be made accurate without a code change), that refusal is signal — do not override it; carry it into step 6.

3. **Fact-check** — dispatch `docs-fact-checker` on the docs diff from step 2 **plus** the code diff the docs claim to describe. Give it both file lists explicitly. Its job is truth, scope, and style-vocabulary drift — not wording preferences.

4. **Fix-loop (max 3 iterations):**
   - **Verify findings via `verifier`, not in your own context.** Dispatch `verifier` in finding-check mode with the findings, the file list and the diff; forward only the ones it marks `real`, dropping the rest rather than commissioning performative fixes. If a verdict looks wrong to you on its face, that's the moment to read the code yourself — not by default. (Same `superpowers:receiving-code-review` rigor, applied by a cheaper model whose reading doesn't accumulate in the orchestrator.)
   - Send the SPECIFIC findings back to `docs-writer` (not "address the review"), then re-dispatch `docs-fact-checker` on the new diff. That counts as one iteration.
   - A finding that says "this claim is false because the code does X" means the doc changes, not the code. A finding that means the *code* is wrong leaves this loop entirely — record it for step 6.
   - **Before the third iteration**, if an advisor tool is available, consult it once with the remaining findings and what the previous two fixes tried. Skip this if no advisor is on.
   - Clean check (no false claims, no scope or taxonomy violations) → exit the loop.
   - 3 iterations with findings still open → STOP. Report the unresolved findings to the user and ask how to proceed.

5. **Stale-reference sweep (orchestrator).** For each thing this ticket renamed or removed, run `git grep -il "<old-name>"` and confirm every remaining hit is intentionally historical — hits in the frozen doc directories and in scratch space are fine by design; a hit in a living overview, a `CLAUDE.md`, or a `.claude/` definition is not. New findings feed back into the same bounded loop from step 4.

6. **Report back** — summarise for the caller: which files changed, which claims were verified and against what, the final fact-check status (clean / escalated), anything the writer refused and why, and **any code bugs surfaced along the way** as input for a follow-up dev ticket. Apply `superpowers:verification-before-completion`: every claim of "verified" must be backed by something actually observed during this cycle. Do NOT commit, and do NOT start the next task.
