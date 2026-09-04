# Profile: Java / Maven / Spring Boot

Starting material for a project's `CLAUDE.md`. Copy the sections you need, replace every
`<placeholder>`, and **delete anything that isn't actually true** — a convention the reviewer can't
verify is worse than no convention.

---

## `## Build & Test Commands`

```markdown
## Build & Test Commands

Java and Maven are <on PATH | installed under `<dir>` and NOT on PATH>.

<If off PATH:>
Set `JAVA_HOME` and use full paths. The JDK and Maven versions are bumped in place — run
`ls <toolchain dir>` and take the `<jdk-name>-<major>*` entry rather than trusting a version
written here.

    export JAVA_HOME=<jdk path>
    <maven path>/bin/mvn <goals> -f <repo>/pom.xml

Full suite:            mvn test
One class:             mvn test -pl <module> -Dtest=<ClassName>
Full gate:             mvn clean verify
<Any required env var, e.g. a mirror URL the settings file interpolates.>

**Before core tests see a change to a plugin/sibling module:** `mvn install -DskipTests -pl <module>`
— the consuming module resolves that artifact from the local repository, and a stale one there
builds and runs normally while serving old code.

Tag scheme: `@Tag("<name>")` is <excluded from | the only thing run by> the default run. Do not add
it to a new test unless the brief says to.
```

## `## Conventions` — backend section

```markdown
### Backend (Java <version> + Spring Boot <version>)

- **Component discovery:** <e.g. plugins are Spring `@Component` beans discovered by
  `<Registry>`>. Never hardcode instantiation.
- **DB access:** all queries go through `<DbTemplate-equivalent>`. <Name the one class allowed to
  write SQL against it, if there is one.> Never open a JDBC connection directly.
- **Exceptions:** domain-specific (`<XException>`, …); `<GlobalExceptionHandler>` converts them to
  HTTP responses.
- **Canonical names:** verify hardcoded SQL, column, and field names against `<schema file>` or
  `<generated metadata>` before committing them. <Say which source wins if there are two.>
- **Namespaces:** <e.g. Jackson 3 is `tools.jackson.core`, not `com.fasterxml.jackson.core` —
  except `jackson-annotations`, which still ships under `com.fasterxml.jackson.annotation`.>
- **Config binding:** new config keys go in `<application.yml>` and bind through
  `@ConfigurationProperties` on `<class>`.
- Enum-driven branching uses exhaustive `switch` **expressions** with no `default`, so a new
  constant is a compile error rather than a silent fallthrough.
```

## `## Conventions` — testing section

```markdown
### Testing (JUnit <version>)

- Prefer <integration tests over checked-in fixtures at `<path>`> to isolated unit tests with heavy
  mocking — they're fast and they exercise the real query path.
- New fixture rows/columns: edit `<fixtures source>` and regenerate via `<generator test>` with
  `-D<flag>=true`. Never hand-edit the generated artifact.
- Architecture rules are enforced by `<ArchUnit test>`; if your change needs to cross a boundary it
  forbids, that's a design conversation, not a test to relax.
```

---

## Reviewer notes worth adding

Things a `code-reviewer` can only catch if the project states them:

- Any pooled-datasource / driver quirk that silently produces a wrong-but-working setup.
- Row or size guards the code must respect (a max-rows preflight, a concurrency cap).
- Which module is allowed to carry a given dependency, and why keeping it off the others matters
  (a security starter that secures every endpoint the moment it's on the classpath, say).
