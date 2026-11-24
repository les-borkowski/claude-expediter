# Setting up a project for `expediter`

The plugin's agents and commands are stack-neutral on purpose. Everything they need to know about
*your* project — how to build it, how to test it, what the conventions are, which docs are living
and which are frozen — comes from the project's own `CLAUDE.md`.

This file is the contract. A project that satisfies it gets the full workflow; a project that
satisfies none of it still works, but the commands will stop to ask you things they could have read.

---

## The contract

Add these sections to the project's root `CLAUDE.md`. Section headings matter — the commands look for
them by name.

### `## Build & Test Commands` — **required**

Read by: `/build-feature`, `/build-ticket`, `/build-ui-ticket`,
`feature-implementer`, `test-writer`.

State, as copy-pasteable commands:

- Build the project.
- Run the full test suite.
- Run **one** test class / file / case.
- Any build step that must run *before* tests see a change (installing a module into a local
  artifact cache, generating sources, compiling assets).
- Whether the toolchain is on `PATH`. If it isn't, give the absolute paths and the environment
  variables that must be set.

> **Don't pin a version you won't maintain.** Toolchains get bumped in place, and a pinned version
> in a doc eventually points at a directory that no longer exists. Either say how to discover the
> current one (`ls <toolchain dir>`, take the `<name>-<major>*` entry) or accept that the commands
> will verify it before use — they are instructed to.

### `## Dev Servers` — required only for `/build-ui-ticket`

Read by: `/build-ui-ticket`, `/build-feature`, and the browser-verification step of
`/build-ticket`.

State:

- The command(s) that start the app, and the URL(s) they serve on.
- **A lightweight or fixture-backed startup mode, if one exists**, and what it trades away. This is
  the single biggest time saver in `/build-ui-ticket`: a backend that loads a large production
  dataset at boot can cost minutes per start where a fixture-backed one costs seconds.
- Any startup flag that is *unsafe* and why (a skip-the-build flag that silently serves a stale
  artifact is the classic).
- How to stop them cleanly, if killing the build tool doesn't kill the forked process.
- **Optional — only if you run several features at once** (see *Running several features*):
  - `Ports: backend=8080, frontend=5173` — one `name=base` per server, with `{port:backend}` /
    `{port:frontend}` placeholders in the start commands and URLs above (a frontend that proxies to
    the backend takes `{port:backend}` too). A standalone run uses the base ports.
  - `Max instances: 2` — how many copies of the app may run at once on this machine (default 2).
    Set it from RAM: what one copy uses against what you can spare.

  Without a `Ports:` line nothing changes: servers start exactly as documented.

### `## Conventions` — strongly recommended

Read by: `code-reviewer` (this is its entire rulebook beyond generic correctness),
`feature-implementer`, `test-writer`.

State the rules that a reviewer should treat as violations, not preferences:

- Mandated seams — the class or module that owns DB access, HTTP calls, file IO.
- How components are registered and discovered (and therefore what must **not** be hand-instantiated).
- The canonical source of truth for identifiers — schema files, generated types, API specs — and
  the instruction to verify hardcoded names against it.
- Required namespaces, imports, or library choices, and the ones that are banned.
- Frontend: where state lives, how server state is fetched, the form/validation stack, the
  component library.
- Testing: the mocking boundary, the fixture strategy, any tag that excludes a test from the
  default run.

The `profiles/` directory in this plugin has starting material for a Java/Maven/Spring backend and
a React/TypeScript frontend. Copy the relevant one into your `CLAUDE.md` and edit it down to what is
actually true.

### `## Documentation Map` — required only for `/write-docs`

Read by: `docs-writer`, `docs-fact-checker`, `/write-docs`.

State:

- **Living overviews** — the documents that must stay accurate as code changes, by path.
- **Frozen** — the directories that are historical record and must never be retro-edited
  (plans, design records, ADR archives).
- **In-scope surface** — everything a docs ticket may edit. Default if you don't narrow it: the
  living overviews, the `CLAUDE.md` files, the READMEs, and `.claude/agents/*.md` +
  `.claude/commands/*.md`.
- If the overviews share a self-contained visual style (an inline `<style>` block and a fixed class
  vocabulary in HTML), say so — `docs-fact-checker` enforces it.

---

## Workflow artifacts the plugin writes

Both live in the repo and both should be gitignored unless you want them versioned:

| Path | Written by | Purpose |
|---|---|---|
| `.scratch/<feature-slug>/issues/<NN>-<slug>.md` | `/to-tickets` | one file per ticket, dependency-ordered, with blocking edges |
| `.scratch/<feature-slug>/docs-impact.md` | `/build-feature` | one line per committed ticket naming what the docs will need to reflect; `/write-docs` reads it to scope a sweep |

Refined plans go to `docs/<feature>-plan.md` unless your `## Documentation Map` says otherwise.

---

## Optional dependencies

- **`superpowers`** — strongly recommended. The commands call into it at named integration points:
  `using-git-worktrees` (isolation), `test-driven-development` (TDD tickets),
  `receiving-code-review` (verify findings before forwarding), `systematic-debugging` (root cause
  before the next fix iteration), `verification-before-completion` (no unbacked success claims),
  `finishing-a-development-branch` (the merge decision), and `brainstorming`/`writing-plans` for a
  thin input plan. Each integration point is written to be skipped if the skill isn't installed,
  but you lose real discipline that way.
- **`chrome-devtools-mcp`** — required for `/build-ui-ticket`. `frontend-dev` drives the
  browser through it.
- **`frontend-design`** — optional; loaded when a ticket introduces or reshapes UI.
- **`/simplify`** — a Claude Code builtin, used in the optional simplification pass.
- **`warden`** — optional security scan in `/build-ticket` and `/build-ui-ticket`. With the
  `warden` CLI on `PATH` and the repo inside `WARDEN_SCAN_ROOTS` (set it in Claude Code's
  `settings.json` `env` so subagents see it too), every ticket is scanned; open HIGH/CRITICAL
  findings are verified, triaged and fixed in the fix-loop. Without it the step is skipped and the
  report says so.
- **`ponytail`** — optional; keeps implementers to the smallest complete change. Its
  `SubagentStart` hook injects its ruleset into every subagent, including the read-only ones,
  where it only costs tokens and breaks their report formats. Scope it to the agents that write by
  adding `"PONYTAIL_SUBAGENT_MATCHER": "feature-implementer|test-writer|frontend-dev|docs-writer"`
  to Claude Code's `settings.json` `env`. `/drive-tickets` lists the branch's `shortcut:` markers
  in its final report.

## Agent name collisions

The plugin ships an `Explore` agent that deliberately overrides the built-in one (the built-in
inherits the main conversation's model, so on an Opus session every fan-out search is an Opus call;
this one is pinned to haiku). If a project also has its own `.claude/agents/*.md` with any of these
names, remove them or you'll have two definitions competing:

`Explore`, `quick-lookup`, `feature-implementer`, `test-writer`, `code-reviewer`, `frontend-dev`,
`docs-writer`, `docs-fact-checker`.

## Checkpoints, /clear and compaction

A long feature fills the orchestrator's context. expediter keeps a **checkpoint** on disk
(`.scratch/<slug>/checkpoint.md`, or `.scratch/checkpoint.md` outside a feature) and re-injects it
after any `/clear` or compaction via a `SessionStart` hook, so resetting context loses nothing —
including the list of dev servers and MCP servers that need to be running again.

Neither Claude nor a hook can run `/clear` or `/compact` itself, so the plugin covers both cases:

- **Between turns (interactive):** a `Stop` hook watches context size and, past your threshold,
  tells you a reset is ready. Prefer `/clear`: it's free, while `/compact` re-reads the whole
  conversation to summarise it. With a current checkpoint, `/clear` loses nothing. Set the
  threshold in `/config` → expediter → *Nudge to /clear at (tokens)*, to about where you'd compact
  by hand.
- **Mid-batch (`/drive-tickets` runs as one long turn):** only auto-compaction can fire there, so
  lower its trigger to the same point. Either run `/autocompact <tokens>` once (saved to your user
  settings), or set it for this project in `.claude/settings.json`:

  ```json
  { "autoCompactWindow": 400000 }
  ```

  Opus 5.5 and Sonnet 5.5 have a native 1M window and, left alone, auto-compact only near ~967k —
  by which point every turn has been re-reading a huge context. 400k is about where a manual
  40–50% habit lands; lower is cheaper still (minimum 100k). When it fires, the hook
  re-injects the checkpoint on top of the summary, and the checkpoint wins where they disagree.

Optionally, steer what the compaction summary keeps, in the project's `CLAUDE.md`:

```markdown
# Compact instructions

The checkpoint at .scratch/<slug>/checkpoint.md is authoritative for progress. In the summary,
keep only: the current ticket and its state, unresolved findings, and anything decided since the
last checkpoint update. Drop agent reports and diffs that are already committed.
```

**The one-motion reset:** type `/expediter:checkpoint`, press Enter, then immediately type `/clear`
and press Enter. Claude Code queues a command sent mid-response and runs it when the turn ends, so
the checkpoint is written first and the reset follows without you waiting. Swap in `/compact` if
you'd rather keep a conversation summary as well — it costs a full re-read of the context.

Run `/expediter:checkpoint` yourself any time outside `/drive-tickets` — before a break, or before
a `/clear` in an ordinary session. It writes the same file the hook reads.

## Running several features

`/run-features plan-a.md plan-b.md plan-c.md` in one terminal (your strongest model) plans each
feature with you in turn — both approval gates as usual — and as each plan is approved opens a new
Windows Terminal tab in its worktree running `claude --model sonnet --advisor opus
"/expediter:drive-tickets <slug>"`. Without `wt` it prints that line for you to run instead. A single
plan works too. Running one feature by hand (`/plan-feature` + `/drive-tickets`, or `/build-feature`)
is unchanged.

**Dev-server slots.** When the project declares `Ports:` (see `## Dev Servers`), every driver claims
a slot from a ledger shared by all sessions on the machine, `~/.claude/expediter/slots.json`, before
starting the app. Slot *k* runs every server on base port + *k*; the base ports themselves stay free
for your own manual runs. When `Max instances` slots are taken, a driver does its non-UI tickets
first, then waits for a slot. A driver that stops to ask you something stops its app and gives its
slot up, then claims one again and restarts when you answer.

**Status.** `/run-features status`, or `python3 <plugin>/tools/slots.py status` from the repo, lists
every worktree's feature with its checkpoint status, current task and ports.

**Stale slots.** A slot is freed automatically when its worktree is gone, its checkpoint is missing
or `status: done`, or none of its ports has answered and its checkpoint hasn't changed for 30
minutes (a closed tab). Nothing is ever killed: a server still listening keeps its slot, and an app
copy no feature accounts for shows as a `WARNING` in status for you to stop. Free a slot by hand
with `slots.py release <slug>`.

## Recommended user settings (Opus 5.5 / Sonnet 5.5)

These are your settings, not the plugin's — a plugin can't set them. Put them in
`~/.claude/settings.json` (or a project's `.claude/settings.json`):

```json
{
  "subagentModel": "sonnet",
  "advisorModel": "opus",
  "autoCompactWindow": 400000
}
```

- **`subagentModel: "sonnet"`** — the default for any subagent that would otherwise inherit your
  session model: `general-purpose`, forks, other plugins' agents. expediter' own agents pin their
  models already; this catches everything else. Without it, an Opus session silently runs those on
  Opus.
- **`advisorModel: "opus"`** — enables the [advisor](https://code.claude.com/docs/en/advisor) for
  sessions whose main model supports it. A Sonnet session then consults Opus at decision points
  instead of running Opus throughout; the drive and build commands name when (a stuck fix loop, a
  disputed verdict, the final check). Toggling it doesn't break the prompt cache. Each call reads
  the whole transcript at Opus rates, which is one more reason to keep context small with
  checkpoints. `quick-lookup`, `Explore` and `verifier` are told not to call it. On a Pro plan,
  advisor usage counts against your limits like any Opus usage. Turn off with `/advisor off`.
- **`autoCompactWindow`** — see *Checkpoints, /clear and compaction* above.

**The recommended launch for driving tickets:**

```
cd <worktree> && claude --model sonnet --advisor opus
/expediter:drive-tickets <slug>
```

**Effort.** Opus 5.5 defaults to `medium` effort, and at `medium` matches or beats Opus 5 at `high`.
Sonnet 5.5's guidance is `medium` for well-specified agentic work. expediter' agents now pin their
effort explicitly (`medium` for the workers, `low` for lookups) so a session run at `high` or `max`
doesn't carry that into every subagent. If a ticket genuinely needs more, say so in its brief and
dispatch that one agent with a higher effort.
