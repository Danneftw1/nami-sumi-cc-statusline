/** One styled run of a cockpit row, as cockpit.py printed it. */
export type Span = {
  t: string
  c?: string
  b?: boolean
  u?: boolean
  href?: string
}

/** One frame of the cockpit: its rows, when it was drawn, the width it was drawn for. */
export type Frame = {
  rows: Span[][]
  at: number
  columns: number
  error?: string
}

declare module 'claude-code' {
  interface PluginState {
    'neon-sumi': { frame: Frame }
  }
}
