# Profile: React / TypeScript frontend

Starting material for a project's `CLAUDE.md` (root, or a nested one under the frontend tree). Copy
what you need, replace every `<placeholder>`, and **delete anything that isn't actually true**.

---

## `## Build & Test Commands` — frontend section

```markdown
Package manager: <bun | pnpm | npm>.

Tests:        cd <frontend dir> && <pm> run test <path>
Watch:        <pm> run test:watch
Build:        <pm> run build
Typecheck:    <the actual command — verify it exists>
```

> **Verify the typecheck script exists before writing it here.** A `typecheck` script that isn't in
> `package.json` is a command every agent will run and every agent will see fail. If there isn't
> one, write the direct invocation (`./node_modules/.bin/tsc --noEmit`) — and note whether
> `tsconfig` excludes test files, because if it does, a clean typecheck says nothing about them.

## `## Dev Servers`

```markdown
## Dev Servers

Frontend on **:<port>** (proxies `<api prefix>` to the backend on **:<port>**).

    <start backend command>
    <start frontend command>

- **<lightweight/fixture mode flag>** — <what it does and what it costs>. This is the right mode for
  browser verification; drop it only when the check genuinely needs <real data volume>.
- **Do not use <skip-build flag>** except on a repeat start in a session that already built this
  checkout: it resolves modules from <shared cache> and a stale artifact there boots normally while
  silently serving old code.
- Stopping: <if killing the task doesn't kill a forked process, say how to find and kill it>.
```

## `## Conventions` — frontend section

```markdown
### Frontend (React <version> + TypeScript + <bundler> + <component library>)

- **Where things live:** <e.g. wizard steps in `src/components/wizard/steps/`; each owns its local
  state>. Co-locate helpers next to the component that uses them.
- **State:** <e.g. no central Redux/Context store — don't add one>. Forms use
  <React Hook Form + Zod>.
- **Server state** goes through the <TanStack Query> hooks in `<src/api/>` (typed <axios> client).
  Never `useState` for server data, never a raw `fetch`.
- **Components:** use <library> — <note what you get for free, e.g. ARIA>. Shared config lives in
  `<gridDefaults.ts / theme.ts>`.
- **Tests:** <Vitest> + <MSW> handlers at `<path>` + `<renderWithProviders>`. Mock at the network
  boundary — never stub axios or `fetch` directly. Query the way a user interacts, not by test id
  unless there's no alternative.
```

---

## Reviewer notes worth adding

Things a `code-reviewer` can only catch if the project states them:

- The state rule stated as a **violation**, not a preference ("server state in `useState` is a
  finding").
- Any component of the UI kit that must not be used directly, and what wraps it.
- Test-flake causes the project has already diagnosed — a reviewer that knows the cause stops
  approving the retry that hides it.
