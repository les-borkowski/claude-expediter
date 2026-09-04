# dev-loops

A Claude Code plugin: a subagent workflow that takes a feature plan to a reviewed branch without the
orchestrator ever editing code itself.

Four loop commands, eight role agents, three supporting skills. Stack-neutral — everything
project-specific is read from the project's own `CLAUDE.md` (see [SETUP.md](SETUP.md)).

## Install

```
/plugin marketplace add <git url or local path to this repo>
/plugin install dev-loops@dev-loops-marketplace
```

For a local checkout, `/plugin marketplace add C:/Projects/claude-dev-loops` works — the marketplace
manifest lives in this same repo.

Then set the project up per [SETUP.md](SETUP.md). The minimum that makes the loops useful is a
`## Build & Test Commands` section in the project's `CLAUDE.md`.

## The shape of it

```
/plan-implementer-loop  <plan>        one feature → a reviewable branch
   ├─ refine (codebase-design) → ask open questions          [gate 1]
   ├─ EnterWorktree → feature/<slug>
   ├─ /to-tickets → .scratch/<slug>/issues/NN-*.md           [gate 2]
   └─ per ticket, routed by shape:
        /dev-cycle-loop           ─ implement → test ∥ review → fix (≤3) → report
        /dev-frontend-cycle-loop  ─ implement+browser-verify → test ∥ review → fix (≤3)
        /docs-cycle-loop          ─ write → fact-check → stale-ref sweep → fix (≤3)
      then commit, record docs impact, advance
```

## Commands

| Command | Runs | Notes |
|---|---|---|
| `/plan-implementer-loop` | a whole feature | two approval gates, then auto/batch. Never merges. |
| `/dev-cycle-loop` | one non-UI ticket | `feature-implementer` → (`test-writer` ∥ `code-reviewer`) → bounded fix loop |
| `/dev-frontend-cycle-loop` | one UI ticket | `frontend-dev` verifies in a real browser *inside* the implementer |
| `/docs-cycle-loop` | one docs ticket | no build, no tests — verification is fact-checking prose against code |

## Agents

| Agent | Model | Role |
|---|---|---|
| `quick-lookup` | haiku | path:line answers; keeps the orchestrator from grepping in its own context |
| `Explore` | haiku | broad fan-out search; overrides the built-in so it doesn't inherit an Opus session |
| `feature-implementer` | sonnet | follows existing patterns, minimum implementation, runs the tests |
| `test-writer` | sonnet | tests in the repo's own idiom; reports real pass/fail output |
| `code-reviewer` | sonnet | correctness + documented conventions; reports via `ReportFindings`, never edits |
| `frontend-dev` | sonnet | implements *and* drives the changed flow in Chrome before returning |
| `docs-writer` | sonnet | prose only; refuses source edits and refuses to retro-edit frozen plans |
| `docs-fact-checker` | sonnet | traces every claim in a docs diff back to code; never edits |

## Skills

- **`codebase-design`** — deep-module vocabulary; `/plan-implementer-loop` uses it to pick seams and
  implementation order. Includes `DEEPENING` and `DESIGN-IT-TWICE`.
- **`code-review`** — two-axis review (Standards ∥ Spec) in parallel sub-agents, carrying a Fowler
  smell baseline that applies even to a repo that documents nothing.
- **`to-tickets`** — tracer-bullet vertical slices with explicit blocking edges; expand–contract for
  wide refactors. `disable-model-invocation: true`, so it is user- or command-invoked only.

## The invariants worth keeping

These are the parts that took the longest to get right. Don't sand them off:

1. **The orchestrator never edits code.** Every change goes through a subagent, so each stays scoped
   to its role and the orchestrator's context stays clean enough to sequence a whole feature.
2. **Briefs are self-contained.** Never "read the plan file" — inline the goal, the file list, the
   approach, the exact verify criteria. An agent sent to read a plan reads all of it.
3. **Test and review run concurrently, and the reviewer is told so.** Otherwise it reports the
   missing tests you already have an agent writing, and burns a fix iteration on a phantom finding.
4. **Fix loops are bounded at 3, then stop and ask.** Spinning is worse than escalating.
5. **Re-review by resuming the same agent, not spawning a new one.** A warm reviewer costs a short
   exchange; a cold one re-reads everything, up to three times per ticket.
6. **Findings get verified before they get forwarded.** A reviewer is not automatically right.
7. **No success claim without captured output.** "Should work" is not a result.
8. **Docs are their own ticket and their own loop.** Code loops record a docs-impact line; they
   don't write prose.
