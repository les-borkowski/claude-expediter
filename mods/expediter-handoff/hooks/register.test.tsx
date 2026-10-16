import { expect, mock, test } from 'claude-code/testing'

const CHECKPOINT = '# Checkpoint — demo\nupdated: now    status: in-progress\nhandoff: none\n'

const driveCheckpoint = (status: string) =>
  `# Checkpoint — feat\nupdated: x    status: ${status}\nhandoff: /repo/.scratch/feat/handoff.md\nworktree: /repo\n` +
  `## Goal\nShip it\n## Current task\n02 — add the widget\n## Completed\n- 01 — scaffold (abc123, 4 tests, clean)\n## Next\n03\n`

type On = Parameters<typeof mock.clock>[0]

// An in-memory .scratch under cwd /repo; `age` is how old each file's mtime is.
function stubs(on: On, files: Record<string, string> = {}, opts: { age?: number; fork?: 'fail' | 'throw' } = {}) {
  const clock = mock.clock(on)
  const fs = new Map(Object.entries(files))
  const written: string[] = []
  const commands: string[] = []
  const compacted: string[] = []
  const path = (e: unknown) => (e as { path: string }).path
  const children = (dir: string) => {
    const names = new Set<string>()
    for (const p of fs.keys()) {
      if (!p.startsWith(`${dir}/`)) continue
      const [name, ...rest] = p.slice(dir.length + 1).split('/')
      names.add(`${name}${rest.length ? '/' : ''}`)
    }
    return [...names].map(n =>
      n.endsWith('/')
        ? { name: n.slice(0, -1), kind: 'dir', size: 0, mtimeMs: 0, isLink: false }
        : { name: n, kind: 'file', size: 1, mtimeMs: 0, isLink: false })
  }

  on('session.cwd', () => ({ value: '/repo' }))
  on('session.messages', () => ({ value: [{ role: 'user', text: 'hi', toolUses: [] }] }) as never)
  on('ui.toast', () => ({ value: undefined }))
  on('model.fork', () => {
    if (opts.fork === 'throw') throw new Error('prompt too long')
    return { value: opts.fork === 'fail'
      ? { isAnswered: false, reason: 'prompt too long' }
      : { isAnswered: true, text: CHECKPOINT, usage: {} } } as never
  })
  on('fs.exists', (_$, e) => ({ value: fs.has(path(e)) || [...fs.keys()].some(p => p.startsWith(`${path(e)}/`)) }))
  on('fs.read', (_$, e) => ({ value: fs.get(path(e)) ?? '' }) as never)
  on('fs.list', (_$, e) => ({ value: children(path(e)) }) as never)
  on('fs.stat', async () => ({ value: { kind: 'file', size: 1, mtimeMs: (await clock.now()) - (opts.age ?? 0), isLink: false } }) as never)
  on('fs.write', (_$, e) => {
    written.push(path(e))
    fs.set(path(e), (e as unknown as { text: string }).text)
    return { value: undefined }
  })
  on('command.run', { command: 'clear' }, (_$, e) => {
    commands.push(e.command)
    return { text: 'cleared' }
  })
  on('tool.call', { tool: 'Bash' }, () => ({ result: { stdout: 'ran', stderr: '', interrupted: false } }) as never)
  on('session.compact', () => {
    compacted.push('core')
    return { messages: [{ role: 'user', text: 'summary', toolUses: [] }] } as never
  })
  on('agent.spawn', () => ({ model: 'sonnet', agentId: 'a1' }))
  return { clock, written, commands, compacted }
}

const DRIVING = {
  '/repo/.scratch/feat/checkpoint.md': driveCheckpoint('in-progress'),
  '/repo/.scratch/feat/handoff.md': 'h',
  '/repo/.scratch/feat/issues/01-scaffold.md': 'x',
  '/repo/.scratch/feat/issues/02-widget.md': 'x',
  '/repo/.scratch/feat/issues/03-docs.md': 'x',
}

test('auto_clear on: writes checkpoint then clears', async ($, on) => {
  const s = stubs(on)
  const r = await $.command.run({ command: 'handoff' } as never)
  expect(s.written).toEqual(['/repo/.scratch/checkpoint.md'])
  expect(r.text).toContain('Clearing')
  await s.clock.advance(600)
  expect(s.commands).toEqual(['clear'])
})

test('auto_clear off: writes checkpoint, does not clear', { options: { auto_clear: false } }, async ($, on) => {
  const s = stubs(on)
  const r = await $.command.run({ command: 'handoff' } as never)
  await s.clock.advance(600)
  expect(s.written.length).toBe(1)
  expect(s.commands).toEqual([])
  expect(r.text).toContain('Now /clear')
})

test('guard: push and merge are denied mid-drive, merge-base is not', async ($, on) => {
  stubs(on, DRIVING)
  for (const command of ['git push origin feature/feat', 'cd /repo && git merge main', 'git -C /repo push', 'gh pr merge 12']) {
    const r = await $.tool.call({ tool: 'Bash', command })
    expect(r.deny).toContain('/drive-tickets')
  }
  const base = await $.tool.call({ tool: 'Bash', command: 'git merge-base HEAD master' })
  expect(base.deny).toBeUndefined()
})

test('guard: push is allowed once the drive is done', async ($, on) => {
  stubs(on, { ...DRIVING, '/repo/.scratch/feat/checkpoint.md': driveCheckpoint('done') })
  const r = await $.tool.call({ tool: 'Bash', command: 'git push' })
  expect(r.deny).toBeUndefined()
})

test('guard: push is allowed with no drive', async ($, on) => {
  stubs(on, { '/repo/.scratch/checkpoint.md': CHECKPOINT })
  const r = await $.tool.call({ tool: 'Bash', command: 'git push' })
  expect(r.deny).toBeUndefined()
})

test('guard off: push is allowed mid-drive', { options: { guard_drive: false } }, async ($, on) => {
  stubs(on, DRIVING)
  const r = await $.tool.call({ tool: 'Bash', command: 'git push' })
  expect(r.deny).toBeUndefined()
})

test('compact: refreshes a stale checkpoint first', async ($, on) => {
  const s = stubs(on, { '/repo/.scratch/checkpoint.md': CHECKPOINT }, { age: 60 * 60 * 1000 })
  await $.session.compact({} as never)
  expect(s.written).toEqual(['/repo/.scratch/checkpoint.md'])
  expect(s.compacted).toEqual(['core'])
})

test('compact: leaves a fresh checkpoint alone', async ($, on) => {
  const s = stubs(on, DRIVING, { age: 60 * 1000 })
  await $.session.compact({} as never)
  expect(s.written).toEqual([])
  expect(s.compacted).toEqual(['core'])
})

for (const fork of ['fail', 'throw'] as const) {
  test(`compact: a fork that ${fork === 'fail' ? 'fails' : 'throws'} still compacts`, async ($, on) => {
    const s = stubs(on, { '/repo/.scratch/checkpoint.md': CHECKPOINT }, { fork, age: 60 * 60 * 1000 })
    await $.session.compact({} as never)
    expect(s.written).toEqual([])
    expect(s.compacted).toEqual(['core'])
  })
}

test('compact: a repo without .scratch is left alone', async ($, on) => {
  const s = stubs(on)
  await $.session.compact({} as never)
  expect(s.written).toEqual([])
  expect(s.compacted).toEqual(['core'])
})

test('band: tracks the drive, its stage and review rounds', async ($, on) => {
  stubs(on, DRIVING)
  await $.agent.spawn({ prompt: 'p', subagentType: 'expediter:feature-implementer' } as never)
  await $.agent.spawn({ prompt: 'p', subagentType: 'expediter:code-reviewer' } as never)
  await $.agent.spawn({ prompt: 'p', subagentType: 'expediter:code-reviewer' } as never)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({
      plugin: 'expediter-handoff', surface, component: 'AbovePrompt',
      props: { hasSurvey: false, isWorking: false } as never,
    })
    expect(JSON.stringify(await ui.drawn())).toContain('feat 1/3 · 02 — add the widget · code-reviewer · review 2/3')
  }
})
