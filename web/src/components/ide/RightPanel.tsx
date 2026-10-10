import { useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { loadPanelTab, savePanelTab, type PanelTab } from '../../lib/panelStore'
import { BranchIcon, CheckIcon, CloseIcon, FileIcon } from './icons'
import { ExplorerPanel } from './ExplorerPanel'
import { SourceControlPanel } from './SourceControlPanel'
import { CheckPanel } from './CheckPanel'

const TABS = [
  { id: 'explorer', labelKey: 'ide.explorer', Icon: FileIcon },
  { id: 'sourceControl', labelKey: 'ide.sourceControl', Icon: BranchIcon },
  { id: 'check', labelKey: 'ide.check', Icon: CheckIcon },
] as const satisfies readonly {
  id: PanelTab
  labelKey: string
  Icon: unknown
}[]

interface RightPanelProps {
  projectId: number
  width: number
  onClose: () => void
  onOpenFile: (path: string, line?: number) => void
}

export function RightPanel({ projectId, width, onClose, onOpenFile }: RightPanelProps) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<PanelTab>(() => loadPanelTab(projectId))
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  function selectTab(next: PanelTab) {
    setTab(next)
    savePanelTab(projectId, next)
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    event.preventDefault()
    const index = TABS.findIndex((entry) => entry.id === tab)
    const delta = event.key === 'ArrowRight' ? 1 : -1
    const next = (index + delta + TABS.length) % TABS.length
    selectTab(TABS[next].id)
    tabRefs.current[next]?.focus()
  }

  return (
    <aside
      aria-label={t('ide.panel')}
      style={{ width }}
      className="flex shrink-0 flex-col bg-[var(--surface)] text-sm"
    >
      <div className="flex shrink-0 items-stretch border-b border-[var(--border)]">
        <div
          role="tablist"
          aria-label={t('ide.panel')}
          onKeyDown={handleTabKeyDown}
          className="flex min-w-0 flex-1 items-stretch gap-0.5"
        >
          {TABS.map(({ id, labelKey, Icon }, index) => {
            const active = id === tab
            return (
              <button
                key={id}
                ref={(element) => {
                  tabRefs.current[index] = element
                }}
                type="button"
                role="tab"
                id={`panel-tab-${id}`}
                aria-selected={active}
                aria-label={t(labelKey)}
                title={t(labelKey)}
                tabIndex={active ? 0 : -1}
                onClick={() => selectTab(id)}
                className={`flex shrink-0 items-center justify-center border-b-2 px-2.5 py-1.5 transition ${
                  active
                    ? 'border-b-indigo-500 text-[var(--fg-strong)]'
                    : 'border-b-transparent text-[var(--text-2)] hover:bg-[var(--menu-hover)] hover:text-[var(--fg-2)]'
                }`}
              >
                <Icon width={14} height={14} className="shrink-0" />
              </button>
            )
          })}
        </div>
        <button
          type="button"
          aria-label={t('ide.hidePanel')}
          title={t('ide.hidePanel')}
          onClick={onClose}
          className="flex shrink-0 items-center px-2 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
        >
          <CloseIcon width={14} height={14} />
        </button>
      </div>

      <div
        role="tabpanel"
        aria-labelledby={`panel-tab-${tab}`}
        className="flex min-h-0 flex-1 flex-col"
      >
        {tab === 'explorer' && <ExplorerPanel projectId={projectId} onOpenFile={onOpenFile} />}
        {tab === 'sourceControl' && <SourceControlPanel projectId={projectId} />}
        {tab === 'check' && <CheckPanel projectId={projectId} />}
      </div>
    </aside>
  )
}
