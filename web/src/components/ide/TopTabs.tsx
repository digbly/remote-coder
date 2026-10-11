import { useEffect, useRef, useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { AgentDefinition } from '../../lib/agents'
import type { WorkspaceTab } from '../../lib/workspaceStore'
import { CloseIcon, CommandIcon, PinIcon } from './icons'
import { NewTabMenu } from './NewTabMenu'
import { TabContextMenu } from './TabContextMenu'
import { TAB_DOT_COLORS, tabColorValue } from './tabDisplay'

const DROP_SIDE_CLASS: Record<'before' | 'after', string> = {
  before: 'shadow-[inset_2px_0_0_0_#6366f1]',
  after: 'shadow-[inset_-2px_0_0_0_#6366f1]',
}

interface TopTabsProps {
  tabs: WorkspaceTab[]
  activeId: string | null
  onSelect: (tab: WorkspaceTab) => void
  onClose: (id: string) => void
  onCloseOthers: (id: string) => void
  onCloseToRight: (id: string) => void
  onCloseToLeft: (id: string) => void
  onTogglePin: (id: string) => void
  onRename: (id: string, title: string) => void
  onSetColor: (id: string, color: string | undefined) => void
  onReorder: (sourceId: string, targetId: string, position: 'before' | 'after') => void
  onNew: (agent?: AgentDefinition) => void
  onNewChat: () => void
  onNewBrowser: () => void
}

export function TopTabs({
  tabs,
  activeId,
  onSelect,
  onClose,
  onCloseOthers,
  onCloseToRight,
  onCloseToLeft,
  onTogglePin,
  onRename,
  onSetColor,
  onReorder,
  onNew,
  onNewChat,
  onNewBrowser,
}: TopTabsProps) {
  const { t } = useTranslation()
  const [menu, setMenu] = useState<{ tabId: string; x: number; y: number } | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [dragId, setDragId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<{
    id: string
    position: 'before' | 'after'
  } | null>(null)
  const cancelRenameRef = useRef(false)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  })

  // Ctrl/Cmd+W closes the focused tab, mirroring the shortcut shown in the
  // context menu. Terminals and the remote browser call preventDefault on this
  // key to keep it for the shell/browser, so we only act when they did not.
  useEffect(() => {
    if (activeId == null) return
    const id = activeId
    function onKeyDown(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return
      if (event.key.toLowerCase() !== 'w' || event.defaultPrevented) return
      // Never close background tabs while a modal owns the interaction.
      if (document.querySelector('[aria-modal="true"]')) return
      event.preventDefault()
      onCloseRef.current(id)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [activeId])

  const menuTab = menu ? tabs.find((tab) => tab.id === menu.tabId) ?? null : null
  const menuIndex = menuTab ? tabs.findIndex((tab) => tab.id === menuTab.id) : -1
  const draggingTab = dragId ? tabs.find((tab) => tab.id === dragId) ?? null : null

  function dropPosition(event: DragEvent<HTMLElement>): 'before' | 'after' {
    const rect = event.currentTarget.getBoundingClientRect()
    return event.clientX < rect.left + rect.width / 2 ? 'before' : 'after'
  }

  function beginRename(tab: WorkspaceTab) {
    cancelRenameRef.current = false
    setDraft(tab.title)
    setEditingId(tab.id)
  }

  function commitRename(tab: WorkspaceTab) {
    if (cancelRenameRef.current) return
    onRename(tab.id, draft)
    setEditingId(null)
  }

  function cancelRename() {
    cancelRenameRef.current = true
    setEditingId(null)
  }

  return (
    <div className="flex h-10 shrink-0 items-stretch border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="flex min-w-0 flex-1 items-stretch overflow-x-auto">
        {tabs.map((tab) => {
          const active = tab.id === activeId
          const color = tabColorValue(tab.color)
          const editing = editingId === tab.id
          const dragging = dragId === tab.id
          const canDrop = draggingTab != null && Boolean(draggingTab.pinned) === Boolean(tab.pinned)
          const dropSide = canDrop && dropTarget?.id === tab.id ? dropTarget.position : null
          return (
            <div
              key={tab.id}
              draggable={!editing}
              onDragStart={(event) => {
                setDragId(tab.id)
                event.dataTransfer.effectAllowed = 'move'
                event.dataTransfer.setData('text/plain', tab.id)
              }}
              onDragEnd={() => {
                setDragId(null)
                setDropTarget(null)
              }}
              onDragOver={(event) => {
                if (dragging) return
                if (!canDrop) {
                  setDropTarget((prev) => (prev ? null : prev))
                  return
                }
                event.preventDefault()
                event.dataTransfer.dropEffect = 'move'
                const position = dropPosition(event)
                setDropTarget((prev) =>
                  prev?.id === tab.id && prev.position === position
                    ? prev
                    : { id: tab.id, position },
                )
              }}
              onDrop={(event) => {
                event.preventDefault()
                if (dragId && canDrop && !dragging) {
                  onReorder(dragId, tab.id, dropPosition(event))
                }
                setDragId(null)
                setDropTarget(null)
              }}
              onContextMenu={(event) => {
                event.preventDefault()
                setMenu({ tabId: tab.id, x: event.clientX, y: event.clientY })
              }}
              style={active && color ? { borderTopColor: color } : undefined}
              className={`group relative flex min-w-[120px] flex-1 items-stretch border-r border-[var(--border)] text-[12px] ${
                dragging ? 'opacity-50' : ''
              } ${dropSide ? DROP_SIDE_CLASS[dropSide] : ''} ${
                active
                  ? 'border-t-2 border-t-indigo-500 bg-[var(--active)] text-[var(--fg-strong)]'
                  : 'text-[var(--text-2)] hover:bg-[var(--menu-hover)] hover:text-[var(--fg-2)]'
              }`}
            >
              {editing ? (
                <div className="flex min-w-0 flex-1 items-center gap-2 px-3 pr-7">
                  <TabDot kind={tab.kind} color={color} />
                  <input
                    autoFocus
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        commitRename(tab)
                      } else if (event.key === 'Escape') {
                        event.preventDefault()
                        cancelRename()
                      }
                    }}
                    onBlur={() => commitRename(tab)}
                    aria-label={t('ide.renameTabLabel')}
                    className="w-full min-w-0 rounded border border-indigo-500 bg-[var(--bg)] px-1 py-0.5 text-[12px] text-[var(--fg-strong)] outline-none"
                  />
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => onSelect(tab)}
                  title={tab.title}
                  className="flex min-w-0 flex-1 items-center gap-2 px-3 pr-7 text-left"
                >
                  {tab.pinned && (
                    <PinIcon width={11} height={11} className="shrink-0 text-[var(--muted-2)]" />
                  )}
                  <TabDot kind={tab.kind} color={color} />
                  <span className="truncate">{tab.title}</span>
                </button>
              )}
              {!editing && (
                <button
                  type="button"
                  aria-label={t('ide.closeTab', { title: tab.title })}
                  onClick={() => onClose(tab.id)}
                  className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-[var(--muted-3)] opacity-0 transition hover:bg-[var(--hover-strong)] hover:text-[var(--fg-strong)] group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100"
                >
                  <CloseIcon width={12} height={12} />
                </button>
              )}
            </div>
          )
        })}
        <NewTabMenu onSelect={onNew} onNewChat={onNewChat} onNewBrowser={onNewBrowser} />
      </div>

      <div className="flex shrink-0 items-center gap-2 px-3">
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md bg-[var(--hover)] px-2.5 py-1 text-[12px] text-[var(--fg-2)] transition hover:bg-[var(--hover-strong)]"
        >
          <CommandIcon width={13} height={13} />
          {t('ide.command')}
        </button>
      </div>

      {menuTab && menu && (
        <TabContextMenu
          tab={menuTab}
          x={menu.x}
          y={menu.y}
          closeOthersDisabled={
            tabs.filter((tab) => tab.id !== menuTab.id && !tab.pinned).length === 0
          }
          closeRightDisabled={
            tabs.slice(menuIndex + 1).filter((tab) => !tab.pinned).length === 0
          }
          closeLeftDisabled={
            tabs.slice(0, menuIndex).filter((tab) => !tab.pinned).length === 0
          }
          onCloseTab={() => onClose(menuTab.id)}
          onCloseOthers={() => onCloseOthers(menuTab.id)}
          onCloseRight={() => onCloseToRight(menuTab.id)}
          onCloseLeft={() => onCloseToLeft(menuTab.id)}
          onTogglePin={() => onTogglePin(menuTab.id)}
          onChangeTitle={() => beginRename(menuTab)}
          onSetColor={(color) => onSetColor(menuTab.id, color)}
          onDismiss={() => setMenu(null)}
        />
      )}
    </div>
  )
}

function TabDot({ kind, color }: { kind: WorkspaceTab['kind']; color?: string }) {
  return (
    <span
      className={`h-2 w-2 shrink-0 rounded-sm ${color ? '' : TAB_DOT_COLORS[kind]}`}
      style={color ? { backgroundColor: color } : undefined}
    />
  )
}
