# expediter

A Claude Code plugin: a subagent workflow that takes a feature plan to a reviewed branch without the
orchestrator ever editing code itself.

**Why "expediter".** In a restaurant kitchen the expediter stands at the pass: calls each ticket to
the right station, checks every plate before it goes out, sends back what isn't right, and never
cooks anything. That's the orchestrator here — it routes tickets to role agents, has every result
checked, bounds the send-backs, and never edits code itself.

Seven commands, nine role agents, three supporting skills, two hooks. Stack-neutral — everything
project-specific is read from the project's own `CLAUDE.md` (see [SETUP.md](SETUP.md)).

## Install

```
/plugin marketplace add <git url or local path to this repo>
/plugin install expediter@expediter-marketplace
```

For a local checkout, `/plugin marketplace add C:/Projects/claude-expediter` works — the marketplace
manifest lives in this same repo.

Then set the project up per [SETUP.md](SETUP.md). The minimum that makes the commands useful is a
`## Build & Test Commands` section in the project's `CLAUDE.md`.

## The shape of it

```
/plan-feature <plan>       (strong model)  refine → questions → branch → tickets → handoff.md
      ── new session on Sonnet ──
/drive-tickets <slug>      (Sonnet)        drive every ticket → a reviewable branch

/build-feature  <plan>        both halves in one session — same steps, one model
   ├─ refine (codebase-design) → ask open questions          [gate 1]
   ├─ EnterWorktree → feature/<slug>
   ├─ /to-tickets → .scratch/<slug>/issues/NN-*.md           [gate 2]
   └─ per ticket, routed by shape:
        /build-ticket           ─ implement → test ∥ review → fix (≤3) → report
        /build-ui-ticket  ─ implement+browser-verify → test ∥ review → fix (≤3)
        /write-docs          ─ write → fact-check → stale-ref sweep → fix (≤3)
      then commit, record docs impact, advance
```

## Commands

| Command | Runs | Notes |
|---|---|---|
| `/plan-feature` | planning half | refine, design, tickets, two approval gates; writes `.scratch/<slug>/handoff.md`. Run on your strongest model. |
| `/drive-tickets` | driving half | reads the handoff, drives every ticket, commits per ticket. `model: sonnet`. Never merges. |
| `/checkpoint` | any session | writes the resume checkpoint (goal, current task, done, next, tools to restart). `/clear` then resumes from it. |
| `/build-feature` | a whole feature | both halves in one session. Simpler, but the whole drive runs on the planning model. |
| `/build-ticket` | one non-UI ticket | `feature-implementer` → (`test-writer` ∥ `code-reviewer`) → bounded fix loop |
| `/build-ui-ticket` | one UI ticket | `frontend-dev` verifies in a real browser *inside* the implementer |
| `/write-docs` | one docs ticket | no build, no tests — verification is fact-checking prose against code |
| `/warden-review` | a security review | `warden scan` → `verifier` judges each open HIGH/CRITICAL finding → `warden triage` records it → fixes drafted, applied only if you say so. Needs the `warden` CLI (see SETUP.md). The ticket commands run the same scan automatically. |

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
| `verifier` | sonnet | checks reviewer findings and ticket diffs so the orchestrator doesn't read them itself; ≤25-line verdict |

## Skills

- **`codebase-design`** — deep-module vocabulary; `/build-feature` uses it to pick seams and
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
8. **Docs are their own ticket and their own command.** Code builds record a docs-impact line; they
   don't write prose.

## Stretching a usage-limited plan

Measured on real sessions, most usage went to the **orchestrator on Opus**, not to subagents, which
were already pinned. Hence the split: plan on the strong model, drive on Sonnet. The rest follows
from the same fact — an orchestrator re-reads its whole context every turn, so anything that
keeps that context small pays repeatedly:

- the build commands run on Sonnet (`model: sonnet` in their frontmatter applies for the turn);
- finding verification and complexity-escalation spec checks go to `verifier`, not the orchestrator;
- worker agents return a fixed ≤20-line report instead of a narrative;
- `/code-review`'s two axes are pinned to Sonnet instead of inheriting the session model.

`tools/spend_report.py` breaks your own usage down by model, orchestrator vs subagent, and agent
type (stdlib only: `python3 tools/spend_report.py --since <date>`). Re-run it after a few features
to check the split actually moved the numbers.
- `/drive-tickets` keeps `.scratch/<slug>/checkpoint.md` current after every ticket, and a
  `SessionStart` hook re-injects it after `/clear` or compaction — so you can reset context freely.
  A `Stop` hook tells you when context is large enough that `/clear` (free) beats carrying on or
  compacting. See SETUP.md → *Checkpoints, /clear and compaction*.
- Worker agents pin `effort: medium` (lookups `low`), so a session running at a higher effort
  doesn't pass it down to every subagent.
- Designed to run with Sonnet 5.5 as the orchestrator and **Opus as the advisor**
  (`claude --model sonnet --advisor opus`): the commands consult it only at named decision points, and
  the lookup and verifier agents are told not to. Recommended user settings (`subagentModel`,
  `advisorModel`, `autoCompactWindow`) are in SETUP.md.
