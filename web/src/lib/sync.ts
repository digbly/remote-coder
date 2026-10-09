import { useEffect, useRef, useState } from 'react'
import { workspaceUrl } from './api'
import { emptySyncedState, parseSyncedState, type SyncedState } from './workspaceStore'

const SEND_DEBOUNCE_MS = 200
const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 15000

function newClientId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export interface WorkspaceSync {
  state: SyncedState
  update: (updater: (prev: SyncedState) => SyncedState) => void
}

export function useWorkspaceSync(): WorkspaceSync {
  const [state, setState] = useState<SyncedState>(emptySyncedState)
  const [clientId] = useState(newClientId)

  const stateRef = useRef(state)
  const socketRef = useRef<WebSocket | null>(null)
  const sendTimerRef = useRef<number | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const attemptsRef = useRef(0)

  useEffect(() => {
    let disposed = false

    function sendState(socket: WebSocket, next: SyncedState) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'update', state: next, origin: clientId }))
      }
    }

    function connect() {
      if (disposed) return
      const socket = new WebSocket(workspaceUrl())
      socketRef.current = socket

      socket.onopen = () => {
        attemptsRef.current = 0
      }

      socket.onmessage = (event) => {
        if (disposed) return
        let message: unknown
        try {
          message = JSON.parse(String(event.data))
        } catch {
          return
        }
        if (!isRecord(message) || message.type !== 'state') return
        if (message.origin === clientId) return

        if (message.state === null) {
          // The server has nothing stored yet: seed it with our local state.
          sendState(socket, stateRef.current)
          return
        }

        const parsed = parseSyncedState(message.state)
        if (parsed !== null) {
          if (sendTimerRef.current !== null) {
            window.clearTimeout(sendTimerRef.current)
            sendTimerRef.current = null
          }
          stateRef.current = parsed
          setState(parsed)
        }
      }

      socket.onclose = (event) => {
        if (disposed) return
        socketRef.current = null
        if (event.code === 4401) return // session expired: stop retrying
        attemptsRef.current += 1
        const delay = Math.min(
          RECONNECT_BASE_MS * 2 ** (attemptsRef.current - 1),
          RECONNECT_MAX_MS,
        )
        reconnectTimerRef.current = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      disposed = true
      if (reconnectTimerRef.current !== null) window.clearTimeout(reconnectTimerRef.current)
      if (sendTimerRef.current !== null) window.clearTimeout(sendTimerRef.current)
      const socket = socketRef.current
      socketRef.current = null
      socket?.close()
    }
  }, [clientId])

  function update(updater: (prev: SyncedState) => SyncedState) {
    const next = updater(stateRef.current)
    stateRef.current = next
    setState(next)
    if (sendTimerRef.current !== null) window.clearTimeout(sendTimerRef.current)
    sendTimerRef.current = window.setTimeout(() => {
      sendTimerRef.current = null
      const socket = socketRef.current
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'update', state: next, origin: clientId }))
      }
    }, SEND_DEBOUNCE_MS)
  }

  return { state, update }
}
