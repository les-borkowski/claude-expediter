---
description: Write or refresh the resume checkpoint for the current work — goal, current task, what's done, what's next, and which tools must be running — so /clear or a compaction loses nothing.
argument-hint: "[optional note on what to emphasise]"
---

Write the resume checkpoint for the work in this session. $ARGUMENTS

<!-- No `model:` override on purpose. This summarises the conversation already in context; running
     it on a different model would discard the prompt cache and re-read everything uncached, which
     costs more than letting the current model write a short file. -->

**Where it goes.** If this session is driving a expediter feature (a `.scratch/<slug>/handoff.md`
exists for the work in progress), update `.scratch/<slug>/checkpoint.md`. Otherwise write
`.scratch/checkpoint.md` in the repo root. Create `.scratch/` if needed. Overwrite the previous
checkpoint — it's a snapshot, not a log.

**What goes in it.** Use the template at `${CLAUDE_PLUGIN_ROOT}/templates/checkpoint.md` and fill
every section. The checkpoint is read by a fresh context that has none of this conversation, so:

- **Next** must be concrete enough to act on without re-reading anything.
- **Tools to have running** is the section compaction breaks most often. List every dev server,
  background process, and MCP server this work depends on, each with a *check* command and a
  *start* command. For a dev server, the check is `curl -sf <url>`; for an MCP server, it's "its
  tools appear in the tool list", and the start is "ask the user to reconnect via `/mcp`". Record
  what's running *now*, with real ports and URLs, not what the docs say should be.
- **Completed** is one line per item with its evidence (commit sha, test count). No narrative.
- **Context worth keeping** is for what isn't written down anywhere else. If it's in handoff.md,
  a ticket file, or the code, leave it out — the point is a small file.

Keep the whole thing under ~60 lines. Then end with exactly one line:
`Checkpoint written to <path>. Now /clear (free) or /compact — either resumes from it automatically.`
If the user already queued `/clear` or `/compact` behind this command, it runs as soon as you finish, so
write the file before anything else and keep the reply to that one line.
