import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { fetchFileTree, type FileNode, type FileTree } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { ChevronRightIcon, FileIcon, FolderIcon, RefreshIcon } from './icons'

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
}

function TreeItem({ node, depth, onOpenFile, dirs, onLoadDir }: TreeItemProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const indentation = { paddingLeft: `${depth * 12 + 8}px` }

  if (node.type === 'directory') {
    const dir = dirs[node.path]
    const childIndentation = { paddingLeft: `${(depth + 1) * 12 + 8}px` }

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
          className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-[12.5px] text-[#d7dae0] transition hover:bg-[#24262a]"
        >
          <ChevronRightIcon
            width={12}
            height={12}
            className={`shrink-0 text-[#7d828b] transition ${open ? 'rotate-90' : ''}`}
          />
          <FolderIcon width={14} height={14} className="shrink-0 text-[#7d828b]" />
          <span className="truncate" title={node.path}>
            {node.name}
          </span>
        </button>
        {open && dir?.status === 'loading' && (
          <p style={childIndentation} className="py-1 text-[12px] text-[#7d828b]">
            {t('common.loading')}
          </p>
        )}
        {open && dir?.status === 'error' && (
          <p style={childIndentation} className="py-1 text-[12px] text-[#f0a9b0]">
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
            />
          ))}
        {open && dir?.status === 'loaded' && dir.tree.truncated && (
          <p style={childIndentation} className="py-1 text-[11px] text-[#6b7078]">
            {t('ide.filesTruncated')}
          </p>
        )}
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={() => onOpenFile(node.path)}
      style={indentation}
      title={node.path}
      className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-[12.5px] text-[#c8ccd4] transition hover:bg-[#24262a] hover:text-white"
    >
      <span className="w-3 shrink-0" aria-hidden="true" />
      <FileIcon width={14} height={14} className="shrink-0 text-[#7d828b]" />
      <span className="truncate">{node.name}</span>
    </button>
  )
}

interface ExplorerPanelProps {
  projectId: number
  onOpenFile: (path: string) => void
}

export function ExplorerPanel({ projectId, onOpenFile }: ExplorerPanelProps) {
  return <ExplorerBody key={projectId} projectId={projectId} onOpenFile={onOpenFile} />
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

  const handleRefresh = () => {
    setDirs({})
    setVersion((value) => value + 1)
    reload()
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#8b9099]">
        <span className="truncate">{t('ide.explorer')}</span>
        <button
          type="button"
          aria-label={t('ide.refresh')}
          title={t('ide.refresh')}
          onClick={handleRefresh}
          className="ml-auto rounded p-0.5 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
        >
          <RefreshIcon width={14} height={14} />
        </button>
      </div>

      <div key={version} className="min-h-0 flex-1 overflow-y-auto px-1 pb-3">
        {loading && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#7d828b]">{t('common.loading')}</p>
        )}
        {!loading && error && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#f0a9b0]">{error}</p>
        )}
        {!loading && !error && tree?.entries.length === 0 && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#7d828b]">{t('ide.noFiles')}</p>
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
            />
          ))}
        {!loading && !error && tree?.truncated && (
          <p className="px-2.5 py-2 text-[11px] text-[#6b7078]">{t('ide.filesTruncated')}</p>
        )}
      </div>
    </div>
  )
}
