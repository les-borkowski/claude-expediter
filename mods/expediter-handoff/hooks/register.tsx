import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Drive } from '../types'

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

// Pushes and merges that /drive-tickets must leave to the user. `merge(?![-\w])` lets `git merge-base` through.
const RISKY = /\bgit\s+(?:-C\s+\S+\s+)?(?:push\b|merge(?![-\w]))|\bgh\s+pr\s+merge\b/

// A checkpoint touched this recently is the orchestrator's own; compaction doesn't overwrite it.
const FRESH_MS = 10 * 60 * 1000

const drive = atom({ plugin: 'expediter-handoff', key: 'drive' } as const, null)

type Checkpoint = { path: string; slug?: string; text: string; mtimeMs: number }

// Same candidates as hooks/resume_from_checkpoint.py: .scratch/checkpoint.md and .scratch/*/checkpoint.md under cwd.
async function checkpoints($: EngineInterface): Promise<Checkpoint[]> {
  const dir = `${await $.session.cwd()}/.scratch`
  if (!(await $.fs.exists(dir))) return []
  const found: Checkpoint[] = []
  const add = async (path: string, slug?: string) => {
    if (!(await $.fs.exists(path))) return
    const { mtimeMs } = await $.fs.stat(path)
    found.push({ path, slug, text: await $.fs.read(path), mtimeMs })
  }
  await add(`${dir}/checkpoint.md`)
  for (const entry of await $.fs.list(dir)) {
    if (entry.kind === 'dir') await add(`${dir}/${entry.name}/checkpoint.md`, entry.name)
  }
  return found.sort((a, b) => b.mtimeMs - a.mtimeMs)
}

// A drive is active while a feature checkpoint names a handoff and isn't done.
async function activeDrive($: EngineInterface): Promise<Checkpoint | undefined> {
  return (await checkpoints($)).find(
    c => c.slug !== undefined &&
      !/\bstatus:\s*done\b/.test(c.text) &&
      /^\s*handoff:\s*\S*handoff\.md/m.test(c.text),
  )
}

async function writeCheckpoint($: EngineInterface): Promise<{ path: string } | { reason: string }> {
  const forked = await $.model.fork({ prompt: PROMPT })
  if (!forked.isAnswered) return { reason: forked.reason }

  const text = forked.text.trim()
  const slug = /^\s*handoff:\s*(?:.*\.scratch\/([^/\s]+)\/handoff\.md)/m.exec(text)?.[1]
  const path = `${await $.session.cwd()}/.scratch/${slug ? `${slug}/` : ''}checkpoint.md`
  await $.fs.write(path, text + '\n')
  return { path }
}

function section(text: string, heading: string): string[] {
  const body = text.split(new RegExp(`^## ${heading}.*$`, 'm'))[1]?.split(/^## /m)[0] ?? ''
  return body.split('\n').map(l => l.trim()).filter(Boolean)
}

// Re-reads the active drive into the band's atom; stage and reviews carry over while the task is unchanged.
async function refreshDrive($: EngineInterface): Promise<Drive | null> {
  const c = await activeDrive($)
  if (c === undefined) {
    await update($, drive, () => null)
    return null
  }
  const issues = `${c.path.replace(/checkpoint\.md$/, '')}issues`
  const total = (await $.fs.exists(issues))
    ? (await $.fs.list(issues)).filter(e => e.name.endsWith('.md')).length
    : 0
  const task = (section(c.text, 'Current task')[0] ?? '').replace(/^[-*]\s*/, '')
  const done = section(c.text, 'Completed').filter(l => !/^(none|-\s*none)$/i.test(l)).length
  return update($, drive, prev =>
    prev !== null && prev.slug === c.slug && prev.task === task
      ? { ...prev, done, total }
      : { slug: c.slug!, task, done, total, reviews: 0 },
  )
}

export const register: Register = (on, options) => {
  let nudgedAt = 0

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'handoff',
      description: 'Write the resume checkpoint, then /clear (toggle in plugin options).',
    })
    await refreshDrive($)
    return next(e)
  })

  on('command.run', { command: 'handoff' }, async $ => {
    const r = await writeCheckpoint($)
    if ('reason' in r) return { text: `Checkpoint not written: ${r.reason}.` }

    if (options.auto_clear === false) {
      return { text: `Checkpoint written to ${r.path}. Now /clear — it resumes from it automatically.` }
    }
    // Queued after this command finishes; a command can't clear from inside its own hook.
    $.clock.after(500, () => $.command.run({ command: 'clear' }))
    return { text: `Checkpoint written to ${r.path}. Clearing…` }
  })

  // Subagents included: no one pushes or merges mid-drive. Lifts when step 7 sets `status: done`.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (options.guard_drive === false || !RISKY.test(e.command)) return next(e)
    const c = await activeDrive($)
    if (c === undefined) return next(e)
    return {
      deny: `expediter-handoff: /drive-tickets for "${c.slug}" is still running, and it never pushes or merges. ` +
        `Finish the drive (its checkpoint at ${c.path} gets status: done), then the user picks merge or push. ` +
        `An abandoned drive: set its status to done, or turn off the guard_drive option.`,
    }
  }).catch(($, e, next) => next(e))

  // Refresh the checkpoint before compaction loses the conversation. Never blocks the compaction itself.
  on('session.compact', async ($, e, next) => {
    if (e.trigger === 'precompute' || e.agentId !== undefined || options.checkpoint_on_compact === false) {
      return next(e)
    }
    try {
      const newest = (await checkpoints($))[0]
      // Only where checkpoints are already in use: no .scratch, no fork and no new file.
      if (newest !== undefined && (await $.clock.now()) - newest.mtimeMs > FRESH_MS) {
        const r = await writeCheckpoint($)
        $.ui.toast('path' in r ? `Checkpoint refreshed before compaction: ${r.path}` : `Checkpoint not refreshed: ${r.reason}`)
      }
    } catch {
      $.ui.toast('Checkpoint not refreshed before compaction')
    }
    return next(e)
  }).catch(($, e, next) => next(e))

  on('agent.spawn', async ($, e, next) => {
    const started = await next(e)
    try {
      if ((await refreshDrive($)) !== null) {
        const stage = e.subagentType.replace(/^expediter:/, '')
        await update($, drive, prev =>
          prev && { ...prev, stage, reviews: prev.reviews + (stage === 'code-reviewer' ? 1 : 0) },
        )
      }
    } catch {
      // The band is cosmetic; a failed read never fails the spawn.
    }
    return started
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) return next(e)
    await refreshDrive($).catch(() => null)
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

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const d = await read($, drive)
    if (d === null || e.props.hasSurvey) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    const task = d.task.length > 60 ? `${d.task.slice(0, 59)}…` : d.task
    const parts = [
      `${d.slug} ${d.done}/${d.total || '?'}`,
      task,
      d.stage,
      d.reviews > 0 ? `review ${d.reviews}/3` : undefined,
    ].filter(Boolean)
    return (
      <Box>
        <Text dimColor>▸ {parts.join(' · ')}</Text>
      </Box>
    )
  })
}
