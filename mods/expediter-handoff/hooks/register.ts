import type { Register } from 'claude-code'

const PROMPT = `Write the resume checkpoint for the work in this conversation, as markdown, for a fresh context with none of this conversation. Output ONLY the file content, no preamble. Under 60 lines. Use exactly these sections:

# Checkpoint — <feature slug or short title>
updated: <ISO timestamp>    status: in-progress | blocked | done
handoff: <path to .scratch/<slug>/handoff.md, or none>
worktree: <absolute path the session should be in>
## Goal
## Current task
## Completed   (one line per item: sha, tests, review)
## Next        (concrete enough to act on without re-reading anything)
## Tools to have running   (table: what | check | start; real ports/URLs; "none" if nothing)
## Open issues
## Context worth keeping   (max 10 lines; nothing already in handoff.md, tickets or code)`

export const register: Register = (on, options) => {
  let nudgedAt = 0

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'handoff',
      description: 'Write the resume checkpoint, then /clear (toggle in plugin options).',
    })
    return next(e)
  })

  on('command.run', { command: 'handoff' }, async $ => {
    const root = await $.session.root()
    const forked = await $.model.fork({ prompt: PROMPT })
    if (!forked.isAnswered) return { text: `Checkpoint not written: ${forked.reason}.` }

    const text = forked.text.trim()
    const slug = /^\s*handoff:\s*(?:.*\.scratch\/([^/\s]+)\/handoff\.md)/m.exec(text)?.[1]
    const path = `${root}/.scratch/${slug ? `${slug}/` : ''}checkpoint.md`
    await $.fs.write(path, text + '\n')

    if (options.auto_clear === false) {
      return { text: `Checkpoint written to ${path}. Now /clear — it resumes from it automatically.` }
    }
    // Queued after this command finishes; a command can't clear from inside its own hook.
    $.clock.after(500, () => $.command.run({ command: 'clear' }))
    return { text: `Checkpoint written to ${path}. Clearing…` }
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) return next(e)
    const { context } = await $.session.usage()
    const percent = context.percent ?? 0
    $.ui.status(`ctx ${Math.round(percent)}%`)
    const limit = Number(options.nudge_percent ?? 40)
    if (percent >= limit && percent >= nudgedAt * 1.25) {
      nudgedAt = percent
      $.ui.toast(`Context ${Math.round(percent)}% — /handoff to checkpoint and reset`)
    }
    return next(e)
  })
}
