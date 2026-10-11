import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { WorkspaceTab } from '../../lib/workspaceStore'
import {
  CloseIcon,
  CloseLeftIcon,
  CloseOthersIcon,
  CloseRightIcon,
  PencilIcon,
  PinIcon,
} from './icons'
import { TAB_COLORS } from './tabDisplay'

const MENU_WIDTH = 224
const MENU_MARGIN = 8

interface TabContextMenuProps {
  tab: WorkspaceTab
  x: number
  y: number
  closeOthersDisabled: boolean
  closeRightDisabled: boolean
  closeLeftDisabled: boolean
  onCloseTab: () => void
  onCloseOthers: () => void
  onCloseRight: () => void
  onCloseLeft: () => void
  onTogglePin: () => void
  onChangeTitle: () => void
  onSetColor: (color: string | undefined) => void
  onDismiss: () => void
}

export function TabContextMenu({
  tab,
  x,
  y,
  closeOthersDisabled,
  closeRightDisabled,
  closeLeftDisabled,
  onCloseTab,
  onCloseOthers,
  onCloseRight,
  onCloseLeft,
  onTogglePin,
  onChangeTitle,
  onSetColor,
  onDismiss,
}: TabContextMenuProps) {
  const { t } = useTranslation()
  const menuRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: x, top: y })

  useLayoutEffect(() => {
    const rect = menuRef.current?.getBoundingClientRect()
    if (!rect) return
    const left = Math.min(
      Math.max(MENU_MARGIN, x),
      Math.max(MENU_MARGIN, window.innerWidth - rect.width - MENU_MARGIN),
    )
    const top = Math.min(
      Math.max(MENU_MARGIN, y),
      Math.max(MENU_MARGIN, window.innerHeight - rect.height - MENU_MARGIN),
    )
    setPos({ left, top })
  }, [x, y])

  useEffect(() => {
    menuRef.current?.focus()
  }, [])

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) onDismiss()
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onDismiss()
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('blur', onDismiss)
    window.addEventListener('resize', onDismiss)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('blur', onDismiss)
      window.removeEventListener('resize', onDismiss)
    }
  }, [onDismiss])

  const itemClass =
    'flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[var(--fg-2)] transition hover:bg-[var(--active)] disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent'

  function run(action: () => void) {
    onDismiss()
    action()
  }

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label={t('ide.more')}
      tabIndex={-1}
      style={{ left: pos.left, top: pos.top, width: MENU_WIDTH }}
      onContextMenu={(event) => event.preventDefault()}
      className="fixed z-30 rounded-md border border-[var(--border)] bg-[var(--surface)] py-1 text-[12px] shadow-xl shadow-black/40 outline-none"
    >
      <button type="button" role="menuitem" onClick={() => run(onTogglePin)} className={itemClass}>
        <PinIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
        {tab.pinned ? t('ide.unpinTab') : t('ide.pinTab')}
      </button>

      <div className="my-1 border-t border-[var(--border)]" />

      <button type="button" role="menuitem" onClick={() => run(onCloseTab)} className={itemClass}>
        <CloseIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
        <span className="flex-1">{t('ide.closeTabAction')}</span>
        <span className="text-[11px] text-[var(--muted-3)]">Ctrl+W</span>
      </button>
      <button
        type="button"
        role="menuitem"
        disabled={closeOthersDisabled}
        onClick={() => run(onCloseOthers)}
        className={itemClass}
      >
        <CloseOthersIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
        {t('ide.closeOthers')}
      </button>
      <button
        type="button"
        role="menuitem"
        disabled={closeRightDisabled}
        onClick={() => run(onCloseRight)}
        className={itemClass}
      >
        <CloseRightIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
        {t('ide.closeTabsRight')}
      </button>
      <button
        type="button"
        role="menuitem"
        disabled={closeLeftDisabled}
        onClick={() => run(onCloseLeft)}
        className={itemClass}
      >
        <CloseLeftIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
        {t('ide.closeTabsLeft')}
      </button>

      <div className="my-1 border-t border-[var(--border)]" />

      <button type="button" role="menuitem" onClick={() => run(onChangeTitle)} className={itemClass}>
        <PencilIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
        {t('ide.changeTitle')}
      </button>

      <p className="px-3 pb-1 pt-2 text-[11px] text-[var(--muted-3)]">{t('ide.tabColor')}</p>
      <div className="flex flex-wrap items-center gap-2 px-3 py-1.5">
        <button
          type="button"
          aria-label={t('ide.noColor')}
          aria-pressed={!tab.color}
          title={t('ide.noColor')}
          onClick={() => run(() => onSetColor(undefined))}
          className={`flex h-4 w-4 items-center justify-center rounded-full border ${
            tab.color ? 'border-[var(--muted-3)]' : 'border-[var(--fg-2)]'
          }`}
        >
          <span className="h-3.5 w-[1.5px] rotate-45 rounded-full bg-[var(--muted-3)]" />
        </button>
        {TAB_COLORS.map((color) => (
          <button
            key={color.key}
            type="button"
            aria-label={color.key}
            aria-pressed={tab.color === color.key}
            onClick={() => run(() => onSetColor(color.key))}
            style={{ backgroundColor: color.value }}
            className={`h-4 w-4 rounded-full transition ${
              tab.color === color.key
                ? 'ring-2 ring-[var(--fg-2)] ring-offset-1 ring-offset-[var(--surface)]'
                : ''
            }`}
          />
        ))}
      </div>
    </div>
  )
}
