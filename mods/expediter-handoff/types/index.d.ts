/** The active /drive-tickets run, as the band above the prompt shows it. */
export type Drive = {
  slug: string
  /** First line of the checkpoint's `## Current task`. */
  task: string
  done: number
  total: number
  /** The last expediter agent spawned for this task, without its `expediter:` prefix. */
  stage?: string
  /** code-reviewer spawns since the current task started: the fix round. */
  reviews: number
}

declare module 'claude-code' {
  interface PluginState {
    'expediter-handoff': { drive: Drive | null }
  }
}
