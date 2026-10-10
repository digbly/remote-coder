import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { WorkspaceTab } from '../../lib/workspaceStore'
import { SearchIcon } from './icons'
import { TAB_DOT_COLORS } from './tabDisplay'

const MAX_RESULTS = 50

interface GlobalTabSearchProps {
  tabs: WorkspaceTab[]
  activeId: string | null
  onSelect: (tab: WorkspaceTab) => void
}

function tabSubtitle(tab: WorkspaceTab): string | undefined {
  if (tab.kind === 'editor') return tab.filePath
  if (tab.kind === 'vscode') return tab.worktree
  return tab.worktree ?? tab.agentLabel
}

export function GlobalTabSearch({ tabs, activeId, onSelect }: GlobalTabSearchProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
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
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  function choose(tab: WorkspaceTab) {
    onSelect(tab)
    setQuery('')
    setOpen(false)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (!open || results.length === 0) return
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
    <div ref={rootRef} className="relative">
      <div className="flex items-center gap-1.5 rounded-md bg-[var(--hover)] px-2.5 py-1 text-[12px]">
        <SearchIcon width={13} height={13} className="shrink-0 text-[var(--muted-2)]" />
        <input
          type="text"
          role="combobox"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setHighlight(0)
            setOpen(true)
          }}
          onFocus={() => {
            setHighlight(0)
            setOpen(true)
          }}
          onKeyDown={handleKeyDown}
          placeholder={t('ide.search')}
          aria-label={t('ide.searchOpenTabs')}
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
          className="w-40 bg-transparent text-[var(--fg-2)] placeholder:text-[var(--muted-2)] focus:outline-none"
        />
      </div>
      {open && (
        <div
          id={listboxId}
          role="listbox"
          aria-label={t('ide.searchOpenTabs')}
          className="absolute right-0 z-20 mt-1 max-h-72 w-72 overflow-y-auto rounded-md border border-[var(--border)] bg-[var(--surface)] py-1 text-[12px] shadow-xl shadow-black/40"
        >
          {results.length === 0 ? (
            <p className="px-3 py-1.5 text-[var(--muted-3)]">{t('ide.searchNoResults')}</p>
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
                  className={`flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left transition ${
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
      )}
    </div>
  )
}
