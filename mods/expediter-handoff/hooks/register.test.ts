import { expect, mock, test } from 'claude-code/testing'

const CHECKPOINT = '# Checkpoint — demo\nupdated: now    status: in-progress\nhandoff: none\n'

function stubs(on: Parameters<typeof mock.clock>[0]) {
  const clock = mock.clock(on)
  const written: string[] = []
  const commands: string[] = []
  on('model.fork', () => ({ value: { isAnswered: true, text: CHECKPOINT, usage: {} } }) as never)
  on('session.root', () => ({ value: '/repo' }))
  on('fs.write', (_$, e) => {
    written.push((e as unknown as { path: string }).path)
    return { value: undefined }
  })
  on('command.run', { command: 'clear' }, (_$, e) => {
    commands.push(e.command)
    return { text: 'cleared' }
  })
  return { clock, written, commands }
}

test('auto_clear on: writes checkpoint then clears', async ($, on) => {
  const s = stubs(on)
  const r = await $.command.run({ command: 'handoff' })
  expect(s.written).toEqual(['/repo/.scratch/checkpoint.md'])
  expect(r.text).toContain('Clearing')
  await s.clock.advance(600)
  expect(s.commands).toEqual(['clear'])
})

test('auto_clear off: writes checkpoint, does not clear', { options: { auto_clear: false } }, async ($, on) => {
  const s = stubs(on)
  const r = await $.command.run({ command: 'handoff' })
  await s.clock.advance(600)
  expect(s.written.length).toBe(1)
  expect(s.commands).toEqual([])
  expect(r.text).toContain('Now /clear')
})
