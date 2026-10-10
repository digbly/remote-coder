import { useEffect, useId, useMemo, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { WorkspaceTab } from '../../lib/workspaceStore'
import { SearchIcon } from './icons'
import { TAB_DOT_COLORS } from './tabDisplay'

const MAX_RESULTS = 100

interface TabSearchModalProps {
  tabs: WorkspaceTab[]
  activeId: string | null
  onSelect: (tab: WorkspaceTab) => void
  onClose: () => void
}

function tabSubtitle(tab: WorkspaceTab): string | undefined {
  if (tab.kind === 'editor') return tab.filePath
  if (tab.kind === 'vscode') return tab.worktree
  return tab.worktree ?? tab.agentLabel
}

export function TabSearchModal({ tabs, activeId, onSelect, onClose }: TabSearchModalProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const listboxId = useId()

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const matches = needle
      ? tabs.filter((tab) => tab.title.toLowerCase().includes(needle))
      : tabs
    return matches.slice(0, MAX_RESULTS)
  }, [tabs, query])

  const activeIndex = results.length > 0 ? Math.min(highlight, results.length - 1) : -1

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  function choose(tab: WorkspaceTab) {
    onSelect(tab)
    onClose()
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (results.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlight((value) => (value + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight((value) => (value - 1 + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(results[activeIndex])
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[12vh]"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('ide.searchOpenTabs')}
        onMouseDown={(event) => event.stopPropagation()}
        className="flex w-full max-w-lg flex-col overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)] shadow-2xl shadow-black/50"
      >
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-3.5 py-2.5">
          <SearchIcon width={15} height={15} className="shrink-0 text-[var(--muted-2)]" />
          <input
            type="text"
            role="combobox"
            autoFocus
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setHighlight(0)
            }}
            onKeyDown={handleKeyDown}
            placeholder={t('ide.search')}
            aria-label={t('ide.searchOpenTabs')}
            aria-expanded={results.length > 0}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
            className="w-full bg-transparent text-[13px] text-[var(--fg-2)] placeholder:text-[var(--muted-2)] focus:outline-none"
          />
        </div>
        <div
          id={listboxId}
          role="listbox"
          aria-label={t('ide.searchOpenTabs')}
          className="max-h-[50vh] overflow-y-auto py-1 text-[12px]"
        >
          {results.length === 0 ? (
            <p className="px-3.5 py-2 text-[var(--muted-3)]">{t('ide.searchNoResults')}</p>
          ) : (
            results.map((tab, index) => {
              const subtitle = tabSubtitle(tab)
              const highlighted = index === activeIndex
              return (
                <div
                  key={tab.id}
                  id={`${listboxId}-${index}`}
                  role="option"
                  aria-selected={highlighted}
                  onMouseEnter={() => setHighlight(index)}
                  onClick={() => choose(tab)}
                  className={`flex w-full cursor-pointer items-center gap-2 px-3.5 py-2 text-left transition ${
                    highlighted ? 'bg-[var(--active)]' : 'hover:bg-[var(--menu-hover)]'
                  }`}
                >
                  <span className={`h-2 w-2 shrink-0 rounded-sm ${TAB_DOT_COLORS[tab.kind]}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[var(--fg-2)]">{tab.title}</span>
                    {subtitle && (
                      <span className="block truncate text-[11px] text-[var(--muted-3)]">
                        {subtitle}
                      </span>
                    )}
                  </span>
                  {tab.id === activeId && (
                    <span className="shrink-0 text-[10px] text-[var(--muted-3)]">
                      {t('ide.searchCurrentTab')}
                    </span>
                  )}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
