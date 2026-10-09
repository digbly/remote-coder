import { memo, useEffect, useRef } from 'react'
import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { projectTerminalUrl } from '../../lib/api'

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

    const socket = new WebSocket(
      projectTerminalUrl(projectId, terminalId, { worktree, agentId }),
    )
    socket.binaryType = 'arraybuffer'

    let disposed = false

    function fitNow() {
      try {
        fit.fit()
      } catch {
        /* container not measurable yet */
      }
    }

    function send(message: TerminalMessage) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message))
      }
    }

    function syncSize() {
      fitNow()
      send({ type: 'resize', cols: terminal.cols, rows: terminal.rows })
    }

    socket.onopen = () => {
      syncSize()
      terminal.focus()
    }

    socket.onmessage = (event) => {
      if (disposed) return
      terminal.write(
        typeof event.data === 'string' ? event.data : new Uint8Array(event.data as ArrayBuffer),
      )
    }

    socket.onclose = (event) => {
      if (disposed) return
      const reason =
        event.code === 4401
          ? 'session expired'
          : event.code === 4404
            ? 'project unavailable'
            : 'disconnected'
      terminal.write(`\r\n\x1b[90m[${reason}]\x1b[0m\r\n`)
    }

    const dataDisposable = terminal.onData((data) => send({ type: 'input', data }))

    const resizeObserver = new ResizeObserver(() => syncSize())
    resizeObserver.observe(container)

    return () => {
      disposed = true
      resizeObserver.disconnect()
      dataDisposable.dispose()
      socket.onopen = null
      socket.onmessage = null
      socket.onclose = null
      socket.close()
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
