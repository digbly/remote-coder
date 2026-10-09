import { useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { BranchIcon, CheckIcon, CloseIcon, FileIcon } from './icons'
import { ExplorerPanel } from './ExplorerPanel'
import { SourceControlPanel } from './SourceControlPanel'
import { CheckPanel } from './CheckPanel'

type PanelTab = 'explorer' | 'sourceControl' | 'check'

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
}

export function RightPanel({ projectId, width, onClose }: RightPanelProps) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<PanelTab>('sourceControl')
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  function handleTabKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    event.preventDefault()
    const index = TABS.findIndex((entry) => entry.id === tab)
    const delta = event.key === 'ArrowRight' ? 1 : -1
    const next = (index + delta + TABS.length) % TABS.length
    setTab(TABS[next].id)
    tabRefs.current[next]?.focus()
  }

  return (
    <aside
      aria-label={t('ide.panel')}
      style={{ width }}
      className="flex shrink-0 flex-col bg-[#1b1c1f] text-sm"
    >
      <div className="flex shrink-0 items-stretch border-b border-[#2c2e33]">
        <div
          role="tablist"
          aria-label={t('ide.panel')}
          onKeyDown={handleTabKeyDown}
          className="flex min-w-0 flex-1 items-stretch"
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
                onClick={() => setTab(id)}
                className={`flex min-w-0 flex-1 items-center justify-center border-t-2 px-2 py-2 transition ${
                  active
                    ? 'border-t-indigo-500 bg-[#26282c] text-white'
                    : 'border-t-transparent text-[#9aa0a8] hover:bg-[#222428] hover:text-[#d7dae0]'
                }`}
              >
                <Icon width={15} height={15} className="shrink-0" />
              </button>
            )
          })}
        </div>
        <button
          type="button"
          aria-label={t('ide.hidePanel')}
          title={t('ide.hidePanel')}
          onClick={onClose}
          className="flex shrink-0 items-center px-2 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
        >
          <CloseIcon width={14} height={14} />
        </button>
      </div>

      <div
        role="tabpanel"
        aria-labelledby={`panel-tab-${tab}`}
        className="flex min-h-0 flex-1 flex-col"
      >
        {tab === 'explorer' && <ExplorerPanel projectId={projectId} />}
        {tab === 'sourceControl' && <SourceControlPanel projectId={projectId} />}
        {tab === 'check' && <CheckPanel projectId={projectId} />}
      </div>
    </aside>
  )
}
