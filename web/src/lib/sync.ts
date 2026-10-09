import { useCallback, useEffect, useRef, useState } from 'react'
import { refreshSession, workspaceUrl } from './api'
import { LAYOUT_DEFAULTS } from './layoutStore'
import {
  emptySyncedState,
  parseSyncedState,
  type ProjectWorkspace,
  type SyncedState,
} from './workspaceStore'

const SEND_DEBOUNCE_MS = 200
const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 15000
const MAX_EXPIRED_RECONNECTS = 3

// The whole sidebar layout (visibility and widths) and the active tab are
// per-client UI state: they must not be shared across a user's clients, so they
// are stripped from outgoing state and preserved locally when incoming state is
// applied. Otherwise opening or closing a terminal on one client would overwrite
// the sidebar visibility of every other client.
function stripLocalState(state: SyncedState): SyncedState {
  const workspaces: Record<number, ProjectWorkspace> = {}
  for (const [key, workspace] of Object.entries(state.workspaces)) {
    workspaces[Number(key)] = { tabs: workspace.tabs, activeId: null }
  }
  return {
    workspaces,
    layout: {
      ...state.layout,
      leftOpen: LAYOUT_DEFAULTS.leftOpen,
      leftWidth: LAYOUT_DEFAULTS.leftWidth,
      rightOpen: LAYOUT_DEFAULTS.rightOpen,
      rightWidth: LAYOUT_DEFAULTS.rightWidth,
    },
  }
}

function mergeLocalState(remote: SyncedState, local: SyncedState): SyncedState {
  const workspaces: Record<number, ProjectWorkspace> = {}
  for (const [key, workspace] of Object.entries(remote.workspaces)) {
    const projectId = Number(key)
    const localWorkspace = local.workspaces[projectId]
    const activeId =
      localWorkspace && workspace.tabs.some((tab) => tab.id === localWorkspace.activeId)
        ? localWorkspace.activeId
        : workspace.activeId
    workspaces[projectId] = { tabs: workspace.tabs, activeId }
  }
  return {
    workspaces,
    layout: {
      ...remote.layout,
      leftOpen: local.layout.leftOpen,
      leftWidth: local.layout.leftWidth,
      rightOpen: local.layout.rightOpen,
      rightWidth: local.layout.rightWidth,
    },
  }
}

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
        socket.send(
          JSON.stringify({ type: 'update', state: stripLocalState(next), origin: clientId }),
        )
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
          const merged = mergeLocalState(parsed, stateRef.current)
          stateRef.current = merged
          setState(merged)
        }
      }

      socket.onclose = (event) => {
        if (disposed) return
        socketRef.current = null
        if (event.code === 4401) {
          // Access token expired: refresh the session, then reconnect with
          // backoff (bounded, in case refresh cannot restore the session).
          void refreshSession().then((refreshed) => {
            if (disposed || !refreshed) return
            attemptsRef.current += 1
            if (attemptsRef.current > MAX_EXPIRED_RECONNECTS) return
            const delay = Math.min(
              RECONNECT_BASE_MS * 2 ** (attemptsRef.current - 1),
              RECONNECT_MAX_MS,
            )
            reconnectTimerRef.current = window.setTimeout(connect, delay)
          })
          return
        }
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

  const update = useCallback(
    (updater: (prev: SyncedState) => SyncedState) => {
      const next = updater(stateRef.current)
      stateRef.current = next
      setState(next)
      if (sendTimerRef.current !== null) window.clearTimeout(sendTimerRef.current)
      sendTimerRef.current = window.setTimeout(() => {
        sendTimerRef.current = null
        const socket = socketRef.current
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(
            JSON.stringify({ type: 'update', state: stripLocalState(next), origin: clientId }),
          )
        }
      }, SEND_DEBOUNCE_MS)
    },
    [clientId],
  )

  return { state, update }
}
