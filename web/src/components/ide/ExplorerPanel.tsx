import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  fetchFileTree,
  fetchGitStatus,
  searchProjectFiles,
  type FileNode,
  type FileSearchMode,
  type FileSearchResult,
  type FileTree,
  type GitStatus,
} from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { SearchResultTree } from './SearchResultTree'
import {
  buildGitChangeMaps,
  gitStatusColor,
  gitStatusSignature,
  GIT_STATUS_REFRESH_INTERVAL_MS,
} from './gitStatus'
import {
  ChevronRightIcon,
  FileIcon,
  FolderIcon,
  RefreshIcon,
  SearchIcon,
} from './icons'

type DirState =
  | { status: 'loading' }
  | { status: 'loaded'; tree: FileTree }
  | { status: 'error'; message: string }

interface TreeItemProps {
  node: FileNode
  depth: number
  onOpenFile: (path: string) => void
  dirs: Record<string, DirState>
  onLoadDir: (path: string) => void
  files: Map<string, string>
  changedDirs: Map<string, string>
}

function TreeItem({
  node,
  depth,
  onOpenFile,
  dirs,
  onLoadDir,
  files,
  changedDirs,
}: TreeItemProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const indentation = { paddingLeft: `${depth * 12 + 8}px` }

  if (node.type === 'directory') {
    const dir = dirs[node.path]
    const childIndentation = { paddingLeft: `${(depth + 1) * 12 + 8}px` }
    const dirStatus = changedDirs.get(node.path)

    const toggle = () => {
      const next = !open
      setOpen(next)
      if (next && (dir === undefined || dir.status === 'error')) {
        onLoadDir(node.path)
      }
    }

    return (
      <div>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          style={indentation}
          className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-[12.5px] text-[var(--fg-2)] transition hover:bg-[var(--hover-subtle)]"
        >
          <ChevronRightIcon
            width={12}
            height={12}
            className={`shrink-0 text-[var(--muted-2)] transition ${open ? 'rotate-90' : ''}`}
          />
          <FolderIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
          <span className="truncate" title={node.path}>
            {node.name}
          </span>
          {dirStatus && (
            <span className={`ml-auto shrink-0 font-mono text-[11px] ${gitStatusColor(dirStatus)}`}>
              {dirStatus}
            </span>
          )}
        </button>
        {open && dir?.status === 'loading' && (
          <p style={childIndentation} className="py-1 text-[12px] text-[var(--muted-2)]">
            {t('common.loading')}
          </p>
        )}
        {open && dir?.status === 'error' && (
          <p style={childIndentation} className="py-1 text-[12px] text-[var(--danger)]">
            {dir.message}
          </p>
        )}
        {open &&
          dir?.status === 'loaded' &&
          dir.tree.entries.map((child) => (
            <TreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              onOpenFile={onOpenFile}
              dirs={dirs}
              onLoadDir={onLoadDir}
              files={files}
              changedDirs={changedDirs}
            />
          ))}
        {open && dir?.status === 'loaded' && dir.tree.truncated && (
          <p style={childIndentation} className="py-1 text-[11px] text-[var(--muted-3)]">
            {t('ide.filesTruncated')}
          </p>
        )}
      </div>
    )
  }

  const fileStatus = files.get(node.path)

  return (
    <button
      type="button"
      onClick={() => onOpenFile(node.path)}
      style={indentation}
      title={node.path}
      className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-[12.5px] text-[var(--fg-3-alt)] transition hover:bg-[var(--hover-subtle)] hover:text-[var(--fg-strong)]"
    >
      <span className="w-3 shrink-0" aria-hidden="true" />
      <FileIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
      <span className="truncate">{node.name}</span>
      {fileStatus && (
        <span className={`ml-auto shrink-0 font-mono text-[11px] ${gitStatusColor(fileStatus)}`}>
          {fileStatus}
        </span>
      )}
    </button>
  )
}

interface ExplorerPanelProps {
  projectId: number
  onOpenFile: (path: string, line?: number) => void
}

export function ExplorerPanel({ projectId, onOpenFile }: ExplorerPanelProps) {
  return <ExplorerBody key={projectId} projectId={projectId} onOpenFile={onOpenFile} />
}

interface SearchToggleProps {
  active: boolean
  label: string
  onClick: () => void
  children: string
}

function SearchToggle({ active, label, onClick, children }: SearchToggleProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={label}
      title={label}
      onClick={onClick}
      className={`flex h-6 w-6 items-center justify-center rounded text-[11px] font-medium transition ${
        active
          ? 'bg-indigo-600 text-white'
          : 'text-[var(--muted)] hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]'
      }`}
    >
      {children}
    </button>
  )
}

function ExplorerBody({ projectId, onOpenFile }: ExplorerPanelProps) {
  const { t } = useTranslation()
  const { data: tree, error, loading, reload } = useAsyncData(
    () => fetchFileTree(projectId),
    t('ide.filesError'),
    [projectId],
  )

  const [dirs, setDirs] = useState<Record<string, DirState>>({})
  const [version, setVersion] = useState(0)

  const [gitStatus, setGitStatus] = useState<GitStatus | null>(null)
  const [statusToken, setStatusToken] = useState(0)

  useEffect(() => {
    let active = true
    fetchGitStatus(projectId)
      .then((next) => {
        if (!active) return
        setGitStatus((prev) => (gitStatusSignature(prev) === gitStatusSignature(next) ? prev : next))
      })
      .catch(() => {})
    const timer = window.setInterval(
      () => setStatusToken((value) => value + 1),
      GIT_STATUS_REFRESH_INTERVAL_MS,
    )
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [projectId, statusToken])

  const { files: fileChanges, dirs: changedDirs } = useMemo(
    () => buildGitChangeMaps(gitStatus),
    [gitStatus],
  )

  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<FileSearchMode>('names')
  const [include, setInclude] = useState('')
  const [exclude, setExclude] = useState('')
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [wholeWord, setWholeWord] = useState(false)
  const [regex, setRegex] = useState(false)
  const [result, setResult] = useState<{ query: string; data: FileSearchResult } | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  const loadDir = useCallback(
    (path: string) => {
      setDirs((prev) => ({ ...prev, [path]: { status: 'loading' } }))
      fetchFileTree(projectId, path)
        .then((next) => {
          setDirs((prev) => ({ ...prev, [path]: { status: 'loaded', tree: next } }))
        })
        .catch((err) => {
          setDirs((prev) => ({
            ...prev,
            [path]: {
              status: 'error',
              message: err instanceof Error ? err.message : t('ide.filesError'),
            },
          }))
        })
    },
    [projectId, t],
  )

  const trimmedQuery = query.trim()
  const isStale = result !== null && result.query !== trimmedQuery
  const currentResult = result?.query === trimmedQuery ? result.data : null

  useEffect(() => {
    if (!trimmedQuery) return

    let active = true
    const timer = setTimeout(() => {
      setSearching(true)
      setSearchError(null)
      searchProjectFiles(projectId, trimmedQuery, {
        mode,
        include,
        exclude,
        caseSensitive,
        wholeWord,
        regex,
      })
        .then((next) => {
          if (!active) return
          setResult({ query: trimmedQuery, data: next })
          setSearchError(null)
        })
        .catch((err) => {
          if (!active) return
          setResult(null)
          setSearchError(err instanceof Error ? err.message : t('ide.searchFailed'))
        })
        .finally(() => {
          if (active) setSearching(false)
        })
    }, 250)

    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [
    projectId,
    trimmedQuery,
    mode,
    include,
    exclude,
    caseSensitive,
    wholeWord,
    regex,
    t,
  ])

  const handleRefresh = () => {
    setDirs({})
    setVersion((value) => value + 1)
    setStatusToken((value) => value + 1)
    reload()
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
        <span className="truncate">{t('ide.explorer')}</span>
        <button
          type="button"
          aria-label={t('ide.refresh')}
          title={t('ide.refresh')}
          onClick={handleRefresh}
          className="ml-auto rounded p-0.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
        >
          <RefreshIcon width={14} height={14} />
        </button>
      </div>

      <div className="shrink-0 border-b border-[var(--border)] px-2 pb-2">
        <div className="relative">
          <SearchIcon
            width={13}
            height={13}
            className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-[var(--muted-2)]"
          />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('ide.searchPlaceholder')}
            aria-label={t('ide.searchPlaceholder')}
            className="w-full rounded-md border border-[var(--border)] bg-[var(--bg)] py-1 pl-7 pr-2 text-[12.5px] text-[var(--fg)] outline-none transition focus:border-indigo-500"
          />
        </div>

        <div className="mt-1.5 flex items-center gap-0.5">
          <SearchToggle
            active={caseSensitive}
            label={t('ide.searchMatchCase')}
            onClick={() => setCaseSensitive((value) => !value)}
          >
            Aa
          </SearchToggle>
          <SearchToggle
            active={wholeWord}
            label={t('ide.searchMatchWholeWord')}
            onClick={() => setWholeWord((value) => !value)}
          >
            ab
          </SearchToggle>
          <SearchToggle
            active={regex}
            label={t('ide.searchUseRegex')}
            onClick={() => setRegex((value) => !value)}
          >
            .*
          </SearchToggle>

          <div className="ml-auto grid grid-cols-2 rounded-md bg-[var(--hover-subtle)] p-0.5">
            <button
              type="button"
              aria-pressed={mode === 'names'}
              onClick={() => setMode('names')}
              className={`rounded px-2 py-0.5 text-[11px] font-medium transition ${
                mode === 'names'
                  ? 'bg-[var(--surface)] text-[var(--fg-strong)] shadow-sm'
                  : 'text-[var(--muted)] hover:text-[var(--fg-2)]'
              }`}
            >
              {t('ide.searchNames')}
            </button>
            <button
              type="button"
              aria-pressed={mode === 'contents'}
              onClick={() => setMode('contents')}
              className={`rounded px-2 py-0.5 text-[11px] font-medium transition ${
                mode === 'contents'
                  ? 'bg-[var(--surface)] text-[var(--fg-strong)] shadow-sm'
                  : 'text-[var(--muted)] hover:text-[var(--fg-2)]'
              }`}
            >
              {t('ide.searchContents')}
            </button>
          </div>
        </div>

        <div className="mt-1.5 space-y-1">
          <input
            type="text"
            value={include}
            onChange={(event) => setInclude(event.target.value)}
            placeholder={t('ide.searchIncludePlaceholder')}
            aria-label={t('ide.searchFilesToInclude')}
            className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-[11.5px] text-[var(--fg)] outline-none transition focus:border-indigo-500"
          />
          <input
            type="text"
            value={exclude}
            onChange={(event) => setExclude(event.target.value)}
            placeholder={t('ide.searchExcludePlaceholder')}
            aria-label={t('ide.searchFilesToExclude')}
            className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-[11.5px] text-[var(--fg)] outline-none transition focus:border-indigo-500"
          />
        </div>
      </div>

      <div key={version} className="min-h-0 flex-1 overflow-y-auto px-1 pb-3">
        {trimmedQuery ? (
          <>
            {(searching || isStale) && !searchError && (
              <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">
                {t('common.loading')}
              </p>
            )}
            {!searching && searchError && (
              <p className="px-2.5 py-1.5 text-[13px] text-[var(--danger)]">{searchError}</p>
            )}
            {!searching && !searchError && currentResult && (
              currentResult.entries.length === 0 ? (
                <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">
                  {t('ide.searchNoResults')}
                </p>
              ) : (
                <>
                  <SearchResultTree
                    entries={currentResult.entries}
                    mode={mode}
                    onOpenFile={onOpenFile}
                  />
                  {currentResult.truncated && (
                    <p className="px-2.5 py-2 text-[11px] text-[var(--muted-3)]">
                      {t('ide.searchResultsTruncated')}
                    </p>
                  )}
                </>
              )
            )}
          </>
        ) : (
          <>
            {loading && (
              <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">
                {t('common.loading')}
              </p>
            )}
            {!loading && error && (
              <p className="px-2.5 py-1.5 text-[13px] text-[var(--danger)]">{error}</p>
            )}
            {!loading && !error && tree?.entries.length === 0 && (
              <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">
                {t('ide.noFiles')}
              </p>
            )}
            {!loading &&
              !error &&
              tree?.entries.map((node) => (
                <TreeItem
                  key={node.path}
                  node={node}
                  depth={0}
                  onOpenFile={onOpenFile}
                  dirs={dirs}
                  onLoadDir={loadDir}
                  files={fileChanges}
                  changedDirs={changedDirs}
                />
              ))}
            {!loading && !error && tree?.truncated && (
              <p className="px-2.5 py-2 text-[11px] text-[var(--muted-3)]">
                {t('ide.filesTruncated')}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
