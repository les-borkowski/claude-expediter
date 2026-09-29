---
description: Plan a feature on the strong model — refine the design, ask open questions, create the worktree branch, split into approved tickets — then write a handoff so a cheaper session can drive the tickets with /drive-tickets. Never writes code.
argument-hint: <plan file path or inline plan>
---

Plan this feature up to approved tickets, then hand off: $ARGUMENTS

This is the **planning half** of `/build-feature`. Planning is where a strong model earns its cost: design seams, implementation order, ticket boundaries. Driving tickets afterwards is sequencing — brief, dispatch, verify, commit — and runs well on a cheaper model. Splitting the two across sessions keeps the expensive model's context short and stops it from sitting in a long batch loop re-reading every agent report.

Run this session on your strongest model. It ends at the second approval gate.

**Framing rules (same discipline as build-ticket):**
- You (the orchestrator) do NOT edit code yourself. Every code change flows through `/build-ticket`'s subagents so each stays scoped to its role. You only write plan/ticket artifacts, create the branch, and commit.
- Each ticket brief you pass to `/build-ticket` is a self-contained contract. Do NOT tell it or its subagents to "read the plan file" — inline the specifics (goal, files, approach, exact verify criteria).
- The backend agents (`feature-implementer`, `test-writer`, `code-reviewer`) declare narrow tool allowlists, so they have `Bash` but no `PowerShell` and no MCP tools — a property of those definitions, not a platform limit (`frontend-dev` inherits both). Give them Bash-syntax build commands.
- **Resolve the build and test commands yourself before writing any ticket brief.** Read `## Build & Test Commands` in the project's `CLAUDE.md` (see the plugin's `SETUP.md` for the contract) and pass the resolved commands inline. If the toolchain lives off `PATH` or the doc pins a version, verify it still exists rather than trusting the written version — versions get bumped in place and a pinned one eventually lies.
- **Don't do lookups yourself.** Writing a self-contained ticket brief needs exact file paths and call sites. Dispatch `quick-lookup` (haiku, read-only) for those instead of grepping in your own context — over a whole feature's worth of tickets that adds up, and this orchestrator's context is the one you most want to keep clean.
- Inside this command the recipe governs. Superpowers skills are used at the named integration points below; their own triggers do not restructure the loop. Skip any integration point whose skill isn't installed.


**Steps:**

1. **Ingest & refine.** Read the plan from the argument (a file path, or inline plan text). Incoming plans are usually already detailed — refine, don't re-plan. Only if the input is thin or ambiguous, fall back to `superpowers:brainstorming` → `superpowers:writing-plans` to firm it up first. Apply the `codebase-design` skill to plan the implementation: identify the deep modules and seams the plan implies, name them with the glossary, and decide the implementation order. For a genuinely hard interface decision, optionally fan out `DESIGN-IT-TWICE` sub-agents and compare on depth/locality/seam placement. For a UI-facing feature, also load the `frontend-design` skill so tickets carry concrete visual direction (typography, layout, component intent) instead of leaving it to improvisation. Write the refined plan to the project's plan directory (`docs/<feature>-plan.md` unless the project's `## Documentation Map` says otherwise).

2. **Ask open questions.** If refinement surfaces decisions only the user can make (ambiguous requirements, competing approaches), use `AskUserQuestion` before going further. *(First approval gate.)*

3. **Create the branch in an isolated worktree.** Derive a `<slug>` from the feature name. Follow `superpowers:using-git-worktrees` Step 0 first: if the session is already in a linked worktree, skip creation and use that path. Otherwise use the native `EnterWorktree` tool — `EnterWorktree({ name: "feature-<slug>" })` — to create branch `feature/<slug>` and switch the session into its worktree; do not drop to raw `git worktree add` while the native tool is available. From this point on, every ticket brief, subagent dispatch, and build-file path must point at the worktree's checkout path (as reported by `EnterWorktree`), not the original checkout. All ticket work commits onto `feature/<slug>` inside this worktree.

4. **Split into tickets.** Invoke the `/to-tickets` skill against the refined plan — local-file mode writes one file per ticket to `.scratch/<feature-slug>/issues/<NN>-<slug>.md` in dependency order, with blocking edges. It quizzes the user and iterates until the breakdown is approved. *(Second approval gate.)*
   - *Fallback:* `/to-tickets` is `disable-model-invocation: true`. If it cannot be invoked here, follow its documented vertical-slice process inline (tracer-bullet slices, blocking edges, expand–contract for wide refactors) and write the same `<NN>-<slug>.md` files yourself, then quiz the user for approval.

5. **Write the handoff.** Once tickets are approved, write `.scratch/<feature-slug>/handoff.md`. It is the *only* thing the driving session will know besides the ticket files, so it must be self-contained:
   - Feature slug, branch name, and the **absolute worktree path** reported by `EnterWorktree`.
   - The resolved build and test commands, exactly as verified — not a pointer to `CLAUDE.md`.
   - The refined plan's path, and a 3–6 line summary of the design decisions that constrain implementation (seams chosen, patterns to follow, anything tickets must not re-decide).
   - Ticket order with blocking edges, and per-ticket flags: `TDD`, `ui`, `docs`, `complex`, `opus-reviewer`.
   - Whether any ticket is UI-facing, and the `## Dev Servers` commands to use.

   - Also write `.scratch/<feature-slug>/checkpoint.md` from `${CLAUDE_PLUGIN_ROOT}/templates/checkpoint.md`: status in-progress, 'Current task' = planning complete, 'Next' = run `/drive-tickets <feature-slug>` in a Sonnet session.

6. **Stop and hand off.** Do not start driving tickets in this session. Tell the user, in one short block:
   - where the handoff is,
   - to start a **new session on Sonnet with an Opus advisor** in the worktree path — `claude --model sonnet --advisor opus` from that directory (or plain `claude --model sonnet` if the advisor isn't available on their setup), and
   - to run `/drive-tickets <feature-slug>`.

   A fresh session rather than a `/model` switch here: switching mid-session discards the prompt cache, and the driving session doesn't need any of this session's context — everything it needs is in the handoff and the ticket files.
