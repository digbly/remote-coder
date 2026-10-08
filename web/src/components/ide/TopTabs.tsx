import { useTranslation } from 'react-i18next'
import type { WorkspaceTab } from '../../lib/workspaceStore'
import { CloseIcon, CommandIcon, PlusIcon } from './icons'

interface TopTabsProps {
  tabs: WorkspaceTab[]
  activeId: string | null
  onSelect: (id: string) => void
  onClose: (id: string) => void
  onNew: () => void
}

export function TopTabs({ tabs, activeId, onSelect, onClose, onNew }: TopTabsProps) {
  const { t } = useTranslation()

  return (
    <div className="flex h-10 shrink-0 items-stretch border-b border-[#2c2e33] bg-[#1b1c1f]">
      <div className="flex min-w-0 flex-1 items-stretch overflow-x-auto">
        {tabs.map((tab) => {
          const active = tab.id === activeId
          return (
            <div
              key={tab.id}
              className={`group flex min-w-0 max-w-[220px] items-center gap-2 border-r border-[#2c2e33] px-3 text-[12px] ${
                active
                  ? 'border-t-2 border-t-indigo-500 bg-[#26282c] text-white'
                  : 'text-[#9aa0a8] hover:bg-[#222428] hover:text-[#d7dae0]'
              }`}
            >
              <button
                type="button"
                onClick={() => onSelect(tab.id)}
                className="flex min-w-0 items-center gap-2"
              >
                <span
                  className={`h-2 w-2 shrink-0 rounded-sm ${
                    tab.kind === 'editor' ? 'bg-indigo-400' : 'bg-sky-400'
                  }`}
                />
                <span className="truncate">{tab.title}</span>
              </button>
              <button
                type="button"
                aria-label={t('ide.closeTab', { title: tab.title })}
                onClick={() => onClose(tab.id)}
                className="ml-auto rounded p-0.5 text-[#6b7078] opacity-0 transition hover:bg-[#33363b] hover:text-white group-hover:opacity-100"
              >
                <CloseIcon width={12} height={12} />
              </button>
            </div>
          )
        })}
        <button
          type="button"
          aria-label={t('ide.newTerminal')}
          title={t('ide.newTerminal')}
          onClick={onNew}
          className="flex w-9 shrink-0 items-center justify-center text-[#8b9099] transition hover:bg-[#222428] hover:text-white"
        >
          <PlusIcon />
        </button>
      </div>

      <div className="flex shrink-0 items-center gap-2 px-3">
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md bg-[#2a2c30] px-2.5 py-1 text-[12px] text-[#d7dae0] transition hover:bg-[#33363b]"
        >
          <CommandIcon width={13} height={13} />
          {t('ide.command')}
        </button>
      </div>
    </div>
  )
}
