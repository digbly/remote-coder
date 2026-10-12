import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { CommandDefinition } from '../../lib/workspaceStore'
import { ChevronDownIcon, CommandIcon } from './icons'

const MENU_WIDTH = 240
const MENU_MARGIN = 8

export function CommandsMenu({
  commands,
  onRun,
  onManage,
  placement = 'down',
}: {
  commands: CommandDefinition[]
  onRun: (command: CommandDefinition) => void
  onManage: () => void
  placement?: 'down' | 'up'
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [anchor, setAnchor] = useState<{ top?: number; bottom?: number; left: number } | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const caretRef = useRef<HTMLButtonElement>(null)

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

  function toggleMenu() {
    if (open) {
      setOpen(false)
      return
    }
    const rect = caretRef.current?.getBoundingClientRect()
    if (rect) {
      const left = Math.min(
        Math.max(MENU_MARGIN, rect.right - MENU_WIDTH),
        Math.max(MENU_MARGIN, window.innerWidth - MENU_WIDTH - MENU_MARGIN),
      )
      setAnchor(
        placement === 'up'
          ? { bottom: window.innerHeight - rect.top + 4, left }
          : { top: rect.bottom + 4, left },
      )
    }
    setOpen(true)
  }

  // No commands configured yet: the button opens the manager instead of running.
  if (commands.length === 0) {
    return (
      <button
        type="button"
        onClick={onManage}
        title={t('ide.commandsManage')}
        className="flex items-center gap-1.5 rounded-md bg-[var(--hover)] px-2.5 py-1 text-[12px] text-[var(--fg-2)] transition hover:bg-[var(--hover-strong)]"
      >
        <CommandIcon width={13} height={13} />
        {t('ide.commandsButton')}
      </button>
    )
  }

  const [first] = commands

  return (
    <div ref={rootRef} className="flex items-stretch">
      <button
        type="button"
        onClick={() => onRun(first)}
        title={first.commands.join('\n')}
        className="flex max-w-[14rem] items-center gap-1.5 rounded-l-md bg-[var(--hover)] px-2.5 py-1 text-[12px] text-[var(--fg-2)] transition hover:bg-[var(--hover-strong)]"
      >
        <CommandIcon width={13} height={13} className="shrink-0" />
        <span className="truncate">{first.label}</span>
      </button>
      <button
        ref={caretRef}
        type="button"
        aria-label={t('ide.commandsButton')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggleMenu}
        className="flex items-center rounded-r-md border-l border-[var(--border)] bg-[var(--hover)] px-1 text-[var(--fg-2)] transition hover:bg-[var(--hover-strong)]"
      >
        <ChevronDownIcon width={12} height={12} />
      </button>
      {open && anchor && (
        <div
          role="menu"
          style={{ top: anchor.top, bottom: anchor.bottom, left: anchor.left }}
          className="fixed z-30 max-h-[70vh] w-60 overflow-y-auto rounded-md border border-[var(--border)] bg-[var(--surface)] py-1 text-[12px] shadow-xl shadow-black/40"
        >
          {commands.map((command) => (
            <button
              key={command.id}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                onRun(command)
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--fg-2)] hover:bg-[var(--active)]"
            >
              <CommandIcon width={13} height={13} className="shrink-0" />
              <span className="truncate">{command.label}</span>
            </button>
          ))}
          <div className="my-1 border-t border-[var(--border)]" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onManage()
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--muted-2)] hover:bg-[var(--active)]"
          >
            {t('ide.commandsManage')}
          </button>
        </div>
      )}
    </div>
  )
}
