import { useMemo, useState, type ReactNode } from 'react'
import type { FileSearchEntry, FileSearchMode, SearchSpan } from '../../lib/api'
import { ChevronRightIcon, FileIcon, FolderIcon } from './icons'

interface HighlightedTextProps {
  text: string
  spans: SearchSpan[]
}

function HighlightedText({ text, spans }: HighlightedTextProps) {
  if (spans.length === 0) return <>{text}</>

  // Spans are code-point offsets (computed by the server); slice by code
  // points so astral characters (emoji, etc.) do not offset the highlight.
  const characters = Array.from(text)
  const parts: ReactNode[] = []
  let cursor = 0
  spans.forEach((span, index) => {
    const start = Math.min(Math.max(span.start, cursor), characters.length)
    const end = Math.min(Math.max(span.end, start), characters.length)
    if (start > cursor) parts.push(characters.slice(cursor, start).join(''))
    if (end > start) {
      parts.push(
        <mark key={index} className="rounded-sm bg-yellow-400/40 text-[var(--fg-strong)]">
          {characters.slice(start, end).join('')}
        </mark>,
      )
    }
    cursor = Math.max(cursor, end)
  })
  if (cursor < characters.length) parts.push(characters.slice(cursor).join(''))
  return <>{parts}</>
}

function trimHighlight(text: string, spans: SearchSpan[]): { text: string; spans: SearchSpan[] } {
  const trimmed = text.trimStart()
  const leading = Array.from(text).length - Array.from(trimmed).length
  return {
    text: trimmed,
    spans: spans
      .map((span) => ({ start: span.start - leading, end: span.end - leading }))
      .filter((span) => span.end > 0)
      .map((span) => ({ start: Math.max(0, span.start), end: span.end })),
  }
}

interface SearchTreeNode {
  name: string
  path: string
  children: SearchTreeNode[]
  entry?: FileSearchEntry
}

function sortNodes(nodes: SearchTreeNode[]): void {
  nodes.sort((a, b) => {
    const aDir = a.entry === undefined
    const bDir = b.entry === undefined
    if (aDir !== bDir) return aDir ? -1 : 1
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
  })
  for (const node of nodes) sortNodes(node.children)
}

function buildSearchTree(entries: FileSearchEntry[]): SearchTreeNode[] {
  const root: SearchTreeNode = { name: '', path: '', children: [] }
  const directories = new Map<string, SearchTreeNode>([['', root]])

  for (const entry of entries) {
    const parts = entry.path.split('/')
    let parent = root
    let parentPath = ''
    for (let index = 0; index < parts.length - 1; index += 1) {
      const dirPath = parentPath ? `${parentPath}/${parts[index]}` : parts[index]
      let node = directories.get(dirPath)
      if (!node) {
        node = { name: parts[index], path: dirPath, children: [] }
        directories.set(dirPath, node)
        parent.children.push(node)
      }
      parent = node
      parentPath = dirPath
    }
    parent.children.push({
      name: parts[parts.length - 1],
      path: entry.path,
      children: [],
      entry,
    })
  }

  sortNodes(root.children)
  return root.children
}

interface SearchTreeRowProps {
  node: SearchTreeNode
  depth: number
  mode: FileSearchMode
  onOpenFile: (path: string, line?: number) => void
}

function SearchTreeRow({ node, depth, mode, onOpenFile }: SearchTreeRowProps) {
  const [open, setOpen] = useState(true)
  const indentation = { paddingLeft: `${depth * 12 + 6}px` }

  if (node.entry === undefined) {
    return (
      <div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
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
        </button>
        {open &&
          node.children.map((child) => (
            <SearchTreeRow
              key={child.path}
              node={child}
              depth={depth + 1}
              mode={mode}
              onOpenFile={onOpenFile}
            />
          ))}
      </div>
    )
  }

  const matchIndentation = { paddingLeft: `${(depth + 1) * 12 + 6}px` }

  return (
    <div>
      <button
        type="button"
        onClick={() => onOpenFile(node.path)}
        title={node.path}
        style={indentation}
        className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-[12.5px] text-[var(--fg-3-alt)] transition hover:bg-[var(--hover-subtle)] hover:text-[var(--fg-strong)]"
      >
        <span className="w-3 shrink-0" aria-hidden="true" />
        <FileIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
        <span className="truncate">
          <HighlightedText text={node.name} spans={node.entry.spans} />
        </span>
      </button>
      {mode === 'contents' &&
        node.entry.matches.map((match) => {
          const highlighted = trimHighlight(match.text, match.spans)
          return (
            <button
              type="button"
              key={match.line}
              onClick={() => onOpenFile(node.path, match.line)}
              title={`${node.path}:${match.line}`}
              style={matchIndentation}
              className="flex w-full items-baseline gap-2 rounded px-1.5 py-0.5 text-left transition hover:bg-[var(--hover-subtle)]"
            >
              <span className="shrink-0 text-right text-[11px] tabular-nums text-[var(--muted-3)]">
                {match.line}
              </span>
              <span className="truncate text-[12px] text-[var(--fg-3-alt)]">
                <HighlightedText text={highlighted.text} spans={highlighted.spans} />
              </span>
            </button>
          )
        })}
    </div>
  )
}

interface SearchResultTreeProps {
  entries: FileSearchEntry[]
  mode: FileSearchMode
  onOpenFile: (path: string, line?: number) => void
}

export function SearchResultTree({ entries, mode, onOpenFile }: SearchResultTreeProps) {
  const nodes = useMemo(() => buildSearchTree(entries), [entries])
  return (
    <div>
      {nodes.map((node) => (
        <SearchTreeRow key={node.path} node={node} depth={0} mode={mode} onOpenFile={onOpenFile} />
      ))}
    </div>
  )
}
