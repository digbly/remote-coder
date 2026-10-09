import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { fetchFileTree, type FileNode } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { ChevronRightIcon, FileIcon, FolderIcon, RefreshIcon } from './icons'

function TreeItem({ node, depth }: { node: FileNode; depth: number }) {
  const [open, setOpen] = useState(false)
  const indentation = { paddingLeft: `${depth * 12 + 8}px` }

  if (node.type === 'directory') {
    return (
      <div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
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
        {open &&
          node.children.map((child) => (
            <TreeItem key={child.path} node={child} depth={depth + 1} />
          ))}
      </div>
    )
  }

  return (
    <div
      style={indentation}
      title={node.path}
      className="flex items-center gap-1.5 rounded px-1.5 py-1 text-[12.5px] text-[#c8ccd4]"
    >
      <span className="w-3 shrink-0" aria-hidden="true" />
      <FileIcon width={14} height={14} className="shrink-0 text-[#7d828b]" />
      <span className="truncate">{node.name}</span>
    </div>
  )
}

interface ExplorerPanelProps {
  projectId: number
}

export function ExplorerPanel({ projectId }: ExplorerPanelProps) {
  const { t } = useTranslation()
  const { data: tree, error, loading, reload } = useAsyncData(
    () => fetchFileTree(projectId),
    t('ide.filesError'),
    [projectId],
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#8b9099]">
        <span className="truncate">{t('ide.explorer')}</span>
        <button
          type="button"
          aria-label={t('ide.refresh')}
          title={t('ide.refresh')}
          onClick={reload}
          className="ml-auto rounded p-0.5 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
        >
          <RefreshIcon width={14} height={14} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-1 pb-3">
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
          tree?.entries.map((node) => <TreeItem key={node.path} node={node} depth={0} />)}
        {!loading && !error && tree?.truncated && (
          <p className="px-2.5 py-2 text-[11px] text-[#6b7078]">{t('ide.filesTruncated')}</p>
        )}
      </div>
    </div>
  )
}
