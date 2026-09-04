# Setting up a project for `dev-loops`

The plugin's agents and loops are stack-neutral on purpose. Everything they need to know about
*your* project — how to build it, how to test it, what the conventions are, which docs are living
and which are frozen — comes from the project's own `CLAUDE.md`.

This file is the contract. A project that satisfies it gets the full workflow; a project that
satisfies none of it still works, but the loops will stop to ask you things they could have read.

---

## The contract

Add these sections to the project's root `CLAUDE.md`. Section headings matter — the loops look for
them by name.

### `## Build & Test Commands` — **required**

Read by: `/plan-implementer-loop`, `/dev-cycle-loop`, `/dev-frontend-cycle-loop`,
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
> current one (`ls <toolchain dir>`, take the `<name>-<major>*` entry) or accept that the loops
> will verify it before use — they are instructed to.

### `## Dev Servers` — required only for `/dev-frontend-cycle-loop`

Read by: `/dev-frontend-cycle-loop`, `/plan-implementer-loop`, and the browser-verification step of
`/dev-cycle-loop`.

State:

- The command(s) that start the app, and the URL(s) they serve on.
- **A lightweight or fixture-backed startup mode, if one exists**, and what it trades away. This is
  the single biggest time saver in the frontend loop: a backend that loads a large production
  dataset at boot can cost minutes per start where a fixture-backed one costs seconds.
- Any startup flag that is *unsafe* and why (a skip-the-build flag that silently serves a stale
  artifact is the classic).
- How to stop them cleanly, if killing the build tool doesn't kill the forked process.

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

### `## Documentation Map` — required only for `/docs-cycle-loop`

Read by: `docs-writer`, `docs-fact-checker`, `/docs-cycle-loop`.

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
| `.scratch/<feature-slug>/docs-impact.md` | `/plan-implementer-loop` | one line per committed ticket naming what the docs will need to reflect; `/docs-cycle-loop` reads it to scope a sweep |

Refined plans go to `docs/<feature>-plan.md` unless your `## Documentation Map` says otherwise.

---

## Optional dependencies

- **`superpowers`** — strongly recommended. The loops call into it at named integration points:
  `using-git-worktrees` (isolation), `test-driven-development` (TDD tickets),
  `receiving-code-review` (verify findings before forwarding), `systematic-debugging` (root cause
  before the next fix iteration), `verification-before-completion` (no unbacked success claims),
  `finishing-a-development-branch` (the merge decision), and `brainstorming`/`writing-plans` for a
  thin input plan. Each integration point is written to be skipped if the skill isn't installed,
  but you lose real discipline that way.
- **`chrome-devtools-mcp`** — required for `/dev-frontend-cycle-loop`. `frontend-dev` drives the
  browser through it.
- **`frontend-design`** — optional; loaded when a ticket introduces or reshapes UI.
- **`/simplify`** — a Claude Code builtin, used in the optional simplification pass.

## Agent name collisions

The plugin ships an `Explore` agent that deliberately overrides the built-in one (the built-in
inherits the main conversation's model, so on an Opus session every fan-out search is an Opus call;
this one is pinned to haiku). If a project also has its own `.claude/agents/*.md` with any of these
names, remove them or you'll have two definitions competing:

`Explore`, `quick-lookup`, `feature-implementer`, `test-writer`, `code-reviewer`, `frontend-dev`,
`docs-writer`, `docs-fact-checker`.
