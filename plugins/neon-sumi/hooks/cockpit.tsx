/*
 * The Neon Sumi cockpit as a pane inside Claude Code.
 *
 * `/neon-sumi-cockpit` opens a pane beside the transcript; every two seconds
 * it runs `statusline/cockpit.py --once` at the pane's width and draws the
 * rows it printed, colour for colour. The same script that draws the cockpit
 * in a tmux or iTerm2 split draws it here, so there is one cockpit, not two.
 *
 * The pane is opened only on the person's command, never at session start: an
 * unasked pane waits undrawn below 144 columns, and most terminals are narrower.
 */
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Frame, Span } from '../types'

const PANE = 'neon-sumi-cockpit'
const COMMAND = 'neon-sumi-cockpit'
const REFRESH_MS = 2000
const DEFAULT_COLUMNS = 56
const frame = atom({ plugin: 'neon-sumi', key: 'frame' } as const, { rows: [], at: 0, columns: 0 } as Frame)

// What the render hook last saw: read by the timer, never by the drawing.
// A hot reload starts these over; the pane itself is the engine's and stays.
let wantedColumns = DEFAULT_COLUMNS
let isRunning = false

const RE_TOKEN = /\x1b\[([0-9;:]*)m|\x1b\]8;;(.*?)\x1b\\/g

function hex(r: number, g: number, b: number): string {
  return '#' + [r, g, b].map(n => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0')).join('')
}

/** cockpit.py's ANSI: truecolour foreground, bold, underline, OSC 8 links. */
function spansFromAnsi(text: string): Span[][] {
  const rows: Span[][] = []
  for (const raw of text.replace(/\n+$/, '').split('\n')) {
    const spans: Span[] = []
    let colour: string | undefined
    let bold = false
    let underline = false
    let href: string | undefined
    let pos = 0
    const emit = (chunk: string) => {
      if (!chunk) return
      const span: Span = { t: chunk }
      if (colour) span.c = colour
      if (bold) span.b = true
      if (underline) span.u = true
      if (href && /^https?:\/\//.test(href)) span.href = href
      spans.push(span)
    }
    RE_TOKEN.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = RE_TOKEN.exec(raw)) !== null) {
      emit(raw.slice(pos, m.index))
      pos = m.index + m[0].length
      if (m[0].startsWith('\x1b]')) {
        href = m[2] || undefined
        continue
      }
      const ps = (m[1] || '0').split(/[;:]/)
      for (let i = 0; i < ps.length; i++) {
        const p = ps[i] || '0'
        if (p === '0') {
          colour = undefined
          bold = false
          underline = false
        } else if (p === '1') bold = true
        else if (p === '4') underline = true
        else if (p === '24') underline = false
        else if ((p === '38' || p === '58') && ps[i + 1] === '2' && i + 4 < ps.length) {
          if (p === '38') colour = hex(Number(ps[i + 2]), Number(ps[i + 3]), Number(ps[i + 4]))
          i += 4
        }
      }
    }
    emit(raw.slice(pos))
    rows.push(spans)
  }
  return rows
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: 'Open the Neon Sumi cockpit in a pane: skills, PRs, inbox, ports, boards',
    })
    $.clock.every(REFRESH_MS, () => {
      void refreshIfOpen($)
    })
    return next(e)
  })

  on('command.run', { command: COMMAND }, async $ => {
    const opened = await $.ui.open({ id: PANE, title: 'neon sumi', columns: DEFAULT_COLUMNS })
    void refresh($)
    return { text: opened.isPlaced ? 'Cockpit pane opened.' : `Cockpit pane waits: ${opened.reason}` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Link } = $.ui.resolve(e)
    wantedColumns = Math.max(40, e.props.bodyColumns || DEFAULT_COLUMNS)
    const f = await read($, frame)
    const room = Math.max(1, (e.viewport?.rows ?? 40) - 2)
    if (f.error) {
      return (
        <Box flexDirection="column">
          <Text color="#ff3b5c">cockpit.py failed</Text>
          <Text dimColor wrap="wrap">{f.error}</Text>
        </Box>
      )
    }
    if (!f.at) return <Text dimColor>drawing the cockpit…</Text>
    return (
      <Box flexDirection="column">
        {f.rows.slice(0, room).map(row => (
          <Text wrap="truncate-end">
            {row.length === 0 ? ' ' : row.map(span => (
              span.href
                ? <Link href={span.href}><Text color={span.c} bold={span.b} underline={span.u}>{span.t}</Text></Link>
                : <Text color={span.c} bold={span.b} underline={span.u}>{span.t}</Text>
            ))}
          </Text>
        ))}
      </Box>
    )
  })
}

/** The timer's tick: redraw only while our pane is open (asked of the engine, so a reload cannot forget it). */
async function refreshIfOpen($: EngineInterface) {
  const panes = await $.ui.panes()
  if (panes.some(p => p.id === PANE)) await refresh($)
}

async function refresh($: EngineInterface) {
  if (isRunning) return
  isRunning = true
  const columns = wantedColumns
  try {
    const script = `${$.plugin.root}/statusline/cockpit.py`
    const ran = await $.process.run(['python3', '-B', script, '--once'], {
      env: { COLUMNS: String(columns) },
      timeoutMs: 15000,
    })
    if (ran.exitCode !== 0) {
      await update($, frame, f => ({ ...f, at: Date.now(), columns, error: ran.stderr.trim().split('\n').slice(-3).join('\n') || `exit ${ran.exitCode}` }))
      return
    }
    const rows = spansFromAnsi(ran.stdout)
    await update($, frame, () => ({ rows, at: Date.now(), columns }))
  } catch (err) {
    await update($, frame, f => ({ ...f, at: Date.now(), columns, error: String(err) }))
  } finally {
    isRunning = false
  }
}
