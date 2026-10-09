import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { detectAgents } from '../../lib/api'
import { AGENT_CANDIDATES, type AgentDefinition } from '../../lib/agents'
import { CommandIcon, PlusIcon, TerminalIcon } from './icons'

type DetectionState =
  | { status: 'loading' }
  | { status: 'ready'; agents: AgentDefinition[] }
  | { status: 'error' }

export function NewTabMenu({ onSelect }: { onSelect: (agent?: AgentDefinition) => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null)
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
    if (!open || detection.status !== 'loading') return
    let cancelled = false
    detectAgents(AGENT_CANDIDATES.map((agent) => agent.command))
      .then((statuses) => {
        if (cancelled) return
        const installed = new Set(
          statuses.filter((status) => status.installed).map((status) => status.command),
        )
        setDetection({
          status: 'ready',
          agents: AGENT_CANDIDATES.filter((agent) => installed.has(agent.command)),
        })
      })
      .catch(() => {
        if (!cancelled) setDetection({ status: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [open, detection.status])

  function toggle() {
    if (open) {
      setOpen(false)
      return
    }
    const rect = buttonRef.current?.getBoundingClientRect()
    if (rect) setAnchor({ top: rect.bottom + 4, left: rect.left })
    // Re-detect on every open: newly installed agents show up and an earlier
    // failure can be retried.
    setDetection({ status: 'loading' })
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
        className="flex w-9 shrink-0 items-center justify-center text-[#8b9099] transition hover:bg-[#222428] hover:text-white"
      >
        <PlusIcon />
      </button>
      {open && anchor && (
        <div
          role="menu"
          style={{ top: anchor.top, left: anchor.left }}
          className="fixed z-20 w-52 overflow-hidden rounded-md border border-[#2c2e33] bg-[#1b1c1f] py-1 text-[12px] shadow-xl shadow-black/40"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => choose()}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[#d7dae0] hover:bg-[#26282c]"
          >
            <TerminalIcon width={13} height={13} />
            {t('ide.newTerminal')}
          </button>
          <div className="my-1 border-t border-[#2c2e33]" />
          <p className="px-3 py-1 text-[10px] uppercase tracking-wide text-[#6b7078]">
            {t('ide.agents')}
          </p>
          {detection.status === 'loading' && (
            <p className="px-3 py-1.5 text-[#6b7078]">{t('common.loading')}</p>
          )}
          {detection.status === 'error' && (
            <p className="px-3 py-1.5 text-[#6b7078]">{t('ide.agentsError')}</p>
          )}
          {detection.status === 'ready' && detection.agents.length === 0 && (
            <p className="px-3 py-1.5 text-[#6b7078]">{t('ide.noAgents')}</p>
          )}
          {detection.status === 'ready' &&
            detection.agents.map((agent) => (
              <button
                key={agent.id}
                type="button"
                role="menuitem"
                onClick={() => choose(agent)}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[#d7dae0] hover:bg-[#26282c]"
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
