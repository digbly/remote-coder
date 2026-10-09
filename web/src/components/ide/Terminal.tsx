import { memo, useEffect, useRef } from 'react'
import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { projectTerminalUrl, refreshSession } from '../../lib/api'

const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 15000
const MAX_RECONNECT_ATTEMPTS = 6
const MAX_EXPIRED_RECONNECTS = 3
// A connection that stayed open at least this long is treated as healthy, so
// the backoff counter resets (e.g. after a dev-server reload).
const STABLE_CONNECTION_MS = 3000

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
}: {
  projectId: number
  terminalId: string
  worktree?: string
  agentId?: string
  active: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const lastSizeRef = useRef<{ cols: number; rows: number } | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const terminal = new Terminal({
      cursorBlink: true,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 12.5,
      theme: {
        background: '#0f1012',
        foreground: '#e6e8ec',
        cursor: '#e6e8ec',
      },
    })
    const fit = new FitAddon()
    fitRef.current = fit
    terminal.loadAddon(fit)
    terminal.open(container)
    fitNow()

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

    const resizeObserver = new ResizeObserver(() => syncSize())
    resizeObserver.observe(container)

    return () => {
      disposed = true
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      resizeObserver.disconnect()
      dataDisposable.dispose()
      if (socket) {
        socket.onopen = null
        socket.onmessage = null
        socket.onclose = null
        socket.close()
      }
      terminal.dispose()
      fitRef.current = null
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

  return <div ref={containerRef} className="h-full w-full bg-[#0f1012] px-2 py-1" />
})
