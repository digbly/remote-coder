import { useTranslation } from 'react-i18next'
import type { AgentDefinition } from '../../lib/agents'
import type { WorkspaceTab } from '../../lib/workspaceStore'
import { CloseIcon, CommandIcon } from './icons'
import { NewTabMenu } from './NewTabMenu'
import { TAB_DOT_COLORS } from './tabDisplay'

interface TopTabsProps {
  tabs: WorkspaceTab[]
  activeId: string | null
  onSelect: (tab: WorkspaceTab) => void
  onClose: (id: string) => void
  onNew: (agent?: AgentDefinition) => void
}

export function TopTabs({ tabs, activeId, onSelect, onClose, onNew }: TopTabsProps) {
  const { t } = useTranslation()

  return (
    <div className="flex h-10 shrink-0 items-stretch border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="flex min-w-0 flex-1 items-stretch overflow-x-auto">
        {tabs.map((tab) => {
          const active = tab.id === activeId
          return (
            <div
              key={tab.id}
              className={`group relative flex w-[180px] shrink-0 items-stretch border-r border-[var(--border)] text-[12px] ${
                active
                  ? 'border-t-2 border-t-indigo-500 bg-[var(--active)] text-[var(--fg-strong)]'
                  : 'text-[var(--text-2)] hover:bg-[var(--menu-hover)] hover:text-[var(--fg-2)]'
              }`}
            >
              <button
                type="button"
                onClick={() => onSelect(tab)}
                title={tab.title}
                className="flex min-w-0 flex-1 items-center gap-2 px-3 pr-7 text-left"
              >
                <span className={`h-2 w-2 shrink-0 rounded-sm ${TAB_DOT_COLORS[tab.kind]}`} />
                <span className="truncate">{tab.title}</span>
              </button>
              <button
                type="button"
                aria-label={t('ide.closeTab', { title: tab.title })}
                onClick={() => onClose(tab.id)}
                className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-[var(--muted-3)] opacity-0 transition hover:bg-[var(--hover-strong)] hover:text-[var(--fg-strong)] group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100"
              >
                <CloseIcon width={12} height={12} />
              </button>
            </div>
          )
        })}
        <NewTabMenu onSelect={onNew} />
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
    </div>
  )
}
