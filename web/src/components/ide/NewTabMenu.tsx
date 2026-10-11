import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cachedAgents, fetchAgents, subscribeAgents } from '../../lib/api'
import type { AgentDefinition } from '../../lib/agents'
import { ChatIcon, CommandIcon, PlusIcon, TerminalIcon } from './icons'

type DetectionState =
  | { status: 'loading' }
  | { status: 'ready'; agents: AgentDefinition[] }
  | { status: 'error' }

const MENU_WIDTH = 208
const MENU_MARGIN = 8

export function NewTabMenu({
  onSelect,
  onNewChat,
  placement = 'down',
}: {
  onSelect: (agent?: AgentDefinition) => void
  onNewChat: () => void
  placement?: 'down' | 'up'
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [anchor, setAnchor] = useState<{ top?: number; bottom?: number; left: number } | null>(null)
  const [detection, setDetection] = useState<DetectionState>({ status: 'loading' })
  const buttonRef = useRef<HTMLButtonElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    let cancelled = false

    function apply(agents: AgentDefinition[]) {
      if (!cancelled) {
        setDetection({ status: 'ready', agents: agents.filter((agent) => agent.installed) })
      }
    }

    // Show the cached list instantly and stay subscribed so a background
    // refresh (newly installed agents) lands without reopening the menu.
    const cached = cachedAgents()
    if (cached) apply(cached)
    // The subscription delivers the loaded list (both the first load and
    // background refreshes), so only the failure path needs handling here.
    const unsubscribe = subscribeAgents(apply)

    fetchAgents().catch(() => {
      if (!cancelled && !cached) setDetection({ status: 'error' })
    })

    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [open])

  function toggle() {
    if (open) {
      setOpen(false)
      return
    }
    const rect = buttonRef.current?.getBoundingClientRect()
    if (rect) {
      const left = Math.min(
        Math.max(MENU_MARGIN, rect.left),
        Math.max(MENU_MARGIN, window.innerWidth - MENU_WIDTH - MENU_MARGIN),
      )
      setAnchor(
        placement === 'up'
          ? { bottom: window.innerHeight - rect.top + 4, left }
          : { top: rect.bottom + 4, left },
      )
    }
    // Show cached agents immediately; only fall back to a loading state when
    // nothing has been loaded yet.
    if (!cachedAgents()) setDetection({ status: 'loading' })
    setOpen(true)
  }

  function choose(agent?: AgentDefinition) {
    setOpen(false)
    onSelect(agent)
  }

  return (
    <div ref={rootRef} className="flex">
      <button
        ref={buttonRef}
        type="button"
        aria-label={t('ide.newTerminal')}
        title={t('ide.newTerminal')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggle}
        className="flex w-9 shrink-0 items-center justify-center text-[var(--muted)] transition hover:bg-[var(--menu-hover)] hover:text-[var(--fg-strong)]"
      >
        <PlusIcon />
      </button>
      {open && anchor && (
        <div
          role="menu"
          style={{ top: anchor.top, bottom: anchor.bottom, left: anchor.left }}
          className="fixed z-20 max-h-[70vh] w-52 overflow-y-auto rounded-md border border-[var(--border)] bg-[var(--surface)] py-1 text-[12px] shadow-xl shadow-black/40"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => choose()}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--fg-2)] hover:bg-[var(--active)]"
          >
            <TerminalIcon width={13} height={13} />
            {t('ide.newTerminal')}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onNewChat()
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--fg-2)] hover:bg-[var(--active)]"
          >
            <ChatIcon width={13} height={13} />
            {t('chat.tabTitle')}
          </button>
          <div className="my-1 border-t border-[var(--border)]" />
          <p className="px-3 py-1 text-[10px] uppercase tracking-wide text-[var(--muted-3)]">
            {t('ide.agents')}
          </p>
          {detection.status === 'loading' && (
            <p className="px-3 py-1.5 text-[var(--muted-3)]">{t('common.loading')}</p>
          )}
          {detection.status === 'error' && (
            <p className="px-3 py-1.5 text-[var(--muted-3)]">{t('ide.agentsError')}</p>
          )}
          {detection.status === 'ready' && detection.agents.length === 0 && (
            <p className="px-3 py-1.5 text-[var(--muted-3)]">{t('ide.noAgents')}</p>
          )}
          {detection.status === 'ready' &&
            detection.agents.map((agent) => (
              <button
                key={agent.id}
                type="button"
                role="menuitem"
                onClick={() => choose(agent)}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--fg-2)] hover:bg-[var(--active)]"
              >
                <CommandIcon width={13} height={13} />
                {agent.label}
              </button>
            ))}
        </div>
      )}
    </div>
  )
}
