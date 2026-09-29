# Checkpoint — <feature slug, or a short title for this session's work>

updated: <ISO timestamp>    status: in-progress | blocked | done
handoff: <path to .scratch/<slug>/handoff.md, or none>
worktree: <absolute path the session should be in, or the repo root>

## Goal
<1–3 lines: what this whole piece of work is for. Stable across checkpoints.>

## Current task
<the ticket or step in progress right now, and exactly where it stands —
e.g. "T07: implementer done, test-writer + reviewer dispatched, waiting on both">

## Completed
- <T01 short title> — <commit sha> — tests <N/N> — review <clean|escalated>
- ...one line each. No narrative.

## Next
<the very next action to take on resume, concrete enough to act on without re-reading anything>

## Tools to have running
| what | check | start |
|---|---|---|
| <dev server: backend> | `curl -sf <url>` | `<exact start command, run in background from worktree>` |
| <MCP: chrome-devtools> | its tools appear in your tool list | ask the user to reconnect via `/mcp` |
| <background process / port> | `lsof -i :<port>` | `<command>` |
<"none" if nothing needs to be running>

## Open issues
<escalations awaiting the user, findings still unresolved, anything blocked — or "none">

## Context worth keeping
<at most 10 lines: decisions made during driving, gotchas discovered, anything NOT already in
handoff.md or the ticket files. If it's in those files, don't repeat it here.>
