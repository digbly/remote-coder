import { memo, useEffect, useRef } from 'react'
import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { projectTerminalUrl, refreshSession } from '../../lib/api'
import { useTheme, type ResolvedTheme } from '../../lib/themeContext'
import { useIsMobile } from '../../lib/useMediaQuery'

const MOBILE_KEY_BAR: { label: string; aria: string; data: string }[] = [
  { label: 'Esc', aria: 'Escape', data: '\x1b' },
  { label: 'Tab', aria: 'Tab', data: '\t' },
  { label: 'Ctrl+C', aria: 'Control C', data: '\x03' },
  { label: '←', aria: 'Left arrow', data: '\x1b[D' },
  { label: '↑', aria: 'Up arrow', data: '\x1b[A' },
  { label: '↓', aria: 'Down arrow', data: '\x1b[B' },
  { label: '→', aria: 'Right arrow', data: '\x1b[C' },
  { label: 'PgUp', aria: 'Page up', data: '\x1b[5~' },
  { label: 'PgDn', aria: 'Page down', data: '\x1b[6~' },
]

const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 15000
const MAX_RECONNECT_ATTEMPTS = 6
const MAX_EXPIRED_RECONNECTS = 3
// A connection that stayed open at least this long is treated as healthy, so
// the backoff counter resets (e.g. after a dev-server reload).
const STABLE_CONNECTION_MS = 3000

const TERMINAL_THEMES: Record<
  ResolvedTheme,
  { background: string; foreground: string; cursor: string }
> = {
  light: { background: '#ffffff', foreground: '#1c1e21', cursor: '#1c1e21' },
  dark: { background: '#0f1012', foreground: '#e6e8ec', cursor: '#e6e8ec' },
}

interface TerminalMessage {
  type: 'input' | 'resize'
  data?: string
  cols?: number
  rows?: number
}

export const ProjectTerminal = memo(function ProjectTerminal({
  projectId,
  terminalId,
  worktree,
  agentId,
  active,
  onTitle,
}: {
  projectId: number
  terminalId: string
  worktree?: string
  agentId?: string
  active: boolean
  onTitle?: (projectId: number, terminalId: string, title: string) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const lastSizeRef = useRef<{ cols: number; rows: number } | null>(null)
  const onTitleRef = useRef(onTitle)
  const { resolved } = useTheme()
  const resolvedRef = useRef(resolved)
  const isMobile = useIsMobile()

  function sendKey(data: string) {
    terminalRef.current?.input(data)
  }

  useEffect(() => {
    onTitleRef.current = onTitle
  }, [onTitle])

  useEffect(() => {
    resolvedRef.current = resolved
    const terminal = terminalRef.current
    if (terminal) terminal.options.theme = TERMINAL_THEMES[resolved]
  }, [resolved])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const terminal = new Terminal({
      cursorBlink: true,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 12.5,
      theme: TERMINAL_THEMES[resolvedRef.current],
    })
    terminalRef.current = terminal
    const fit = new FitAddon()
    fitRef.current = fit
    terminal.loadAddon(fit)
    terminal.open(container)
    fitNow()

    // xterm sends Ctrl+C as SIGINT and never touches the clipboard. Intercept
    // Ctrl/Cmd+C to copy the selection when there is one (otherwise the shell
    // still receives SIGINT), and Ctrl/Cmd+V to paste from the clipboard.
    terminal.attachCustomKeyEventHandler((event) => {
      if (event.type !== 'keydown') return true
      const accel = event.ctrlKey || event.metaKey
      if (!accel || event.altKey) return true

      const key = event.key.toLowerCase()
      if (key === 'c' && terminal.hasSelection()) {
        void navigator.clipboard?.writeText(terminal.getSelection()).catch(() => {})
        return false
      }
      if (key === 'v' && navigator.clipboard?.readText) {
        void navigator.clipboard
          .readText()
          .then((text) => {
            if (text) terminal.paste(text)
          })
          .catch(() => {})
        return false
      }
      return true
    })

    let disposed = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let attempts = 0
    let openedAt = 0

    function fitNow() {
      try {
        fit.fit()
      } catch {
        /* container not measurable yet */
      }
    }

    function send(message: TerminalMessage) {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message))
      }
    }

    function syncSize() {
      fitNow()
      const cols = terminal.cols
      const rows = terminal.rows
      const last = lastSizeRef.current
      if (last && last.cols === cols && last.rows === rows) return
      lastSizeRef.current = { cols, rows }
      send({ type: 'resize', cols, rows })
    }

    function writeStatus(text: string) {
      terminal.write(`\r\n\x1b[90m[${text}]\x1b[0m\r\n`)
    }

    function scheduleReconnect() {
      if (disposed || reconnectTimer !== null) return
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** (attempts - 1), RECONNECT_MAX_MS)
      writeStatus('reconnecting…')
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        connect()
      }, delay)
    }

    function connect() {
      if (disposed) return
      const next = new WebSocket(
        projectTerminalUrl(projectId, terminalId, { worktree, agentId }),
      )
      next.binaryType = 'arraybuffer'
      socket = next
      openedAt = 0

      next.onopen = () => {
        openedAt = Date.now()
        // Clear the screen before any server output: a reconnect replays the
        // whole session buffer, which must overwrite rather than append. This
        // also resets the screen when a connection is rejected (accepted then
        // closed with 4401/4404), which is fine since that session is gone.
        terminal.reset()
        // Force one size sync per connection so a resize made by another
        // client while we were away is picked up; the server ignores it when
        // the size is unchanged, so this does not re-trigger SIGWINCH.
        lastSizeRef.current = null
        syncSize()
        terminal.focus()
      }

      next.onmessage = (event) => {
        if (disposed) return
        terminal.write(
          typeof event.data === 'string' ? event.data : new Uint8Array(event.data as ArrayBuffer),
        )
      }

      next.onclose = (event) => {
        if (disposed) return
        socket = null
        // A connection that stayed open long enough is considered healthy, so
        // the backoff resets (for example after a dev-server reload).
        if (openedAt !== 0 && Date.now() - openedAt >= STABLE_CONNECTION_MS) {
          attempts = 0
        }

        if (event.code === 4404) {
          writeStatus('project unavailable')
          return
        }

        attempts += 1
        const expired = event.code === 4401
        const limit = expired ? MAX_EXPIRED_RECONNECTS : MAX_RECONNECT_ATTEMPTS
        if (attempts > limit) {
          writeStatus(expired ? 'session expired' : 'disconnected')
          return
        }

        // The server rejects an expired session before completing the
        // WebSocket handshake, which browsers surface as an opaque 1006. Refresh
        // the session on the first failure of a burst so an expired access
        // token can still recover, then reconnect with backoff.
        if (expired || attempts === 1) {
          void refreshSession().then((refreshed) => {
            if (disposed) return
            if (expired && !refreshed) {
              writeStatus('session expired')
              return
            }
            scheduleReconnect()
          })
          return
        }
        scheduleReconnect()
      }
    }

    connect()

    const dataDisposable = terminal.onData((data) => send({ type: 'input', data }))

    // Programs (agents, shells) announce their own title via an OSC sequence;
    // surface it so the owning tab can rename itself.
    const titleDisposable = terminal.onTitleChange((title) => {
      onTitleRef.current?.(projectId, terminalId, title)
    })

    const resizeObserver = new ResizeObserver(() => syncSize())
    resizeObserver.observe(container)

    return () => {
      disposed = true
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      resizeObserver.disconnect()
      dataDisposable.dispose()
      titleDisposable.dispose()
      if (socket) {
        socket.onopen = null
        socket.onmessage = null
        socket.onclose = null
        socket.close()
      }
      terminal.dispose()
      fitRef.current = null
      terminalRef.current = null
    }
  }, [projectId, terminalId, worktree, agentId])

  useEffect(() => {
    if (!active) return
    try {
      fitRef.current?.fit()
    } catch {
      /* container not measurable yet */
    }
  }, [active])

  return (
    <div className="flex h-full w-full flex-col bg-[var(--bg)]">
      {isMobile && (
        <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-[var(--border)] bg-[var(--surface)] px-1.5 py-1">
          {MOBILE_KEY_BAR.map((key) => (
            <button
              key={key.label}
              type="button"
              tabIndex={-1}
              aria-label={key.aria}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => sendKey(key.data)}
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--btn)] px-2.5 py-1.5 text-xs text-[var(--fg-2)] transition active:bg-[var(--hover)]"
            >
              {key.label}
            </button>
          ))}
        </div>
      )}
      <div ref={containerRef} className="min-h-0 w-full flex-1 px-2 py-1" />
    </div>
  )
})
