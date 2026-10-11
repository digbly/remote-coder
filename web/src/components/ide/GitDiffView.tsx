import { useEffect, useRef, useState } from 'react'
import { DiffEditor, type DiffOnMount } from '@monaco-editor/react'
import { useTranslation } from 'react-i18next'
import { fetchFileDiff } from '../../lib/api'
import { ensureMonaco } from '../../lib/monaco'
import { useTheme } from '../../lib/themeContext'

interface GitDiffViewProps {
  projectId: number
  path: string
  staged: boolean
  origPath?: string | null
  worktree?: string
  active: boolean
}

export function GitDiffView({
  projectId,
  path,
  staged,
  origPath,
  worktree,
  active,
}: GitDiffViewProps) {
  const { t } = useTranslation()
  const { resolved } = useTheme()
  const [oldContent, setOldContent] = useState('')
  const [newContent, setNewContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const editorRef = useRef<Parameters<DiffOnMount>[0] | null>(null)

  useEffect(() => {
    let disposed = false
    Promise.all([fetchFileDiff(projectId, path, staged, origPath, worktree), ensureMonaco()])
      .then(([diff]) => {
        if (disposed) return
        setOldContent(diff.old_content)
        setNewContent(diff.new_content)
        setReady(true)
      })
      .catch((err: unknown) => {
        if (!disposed) setError(err instanceof Error ? err.message : t('ide.diffFailed'))
      })
      .finally(() => {
        if (!disposed) setLoading(false)
      })
    return () => {
      disposed = true
    }
  }, [projectId, path, staged, origPath, worktree, t])

  useEffect(() => {
    if (active) editorRef.current?.layout()
  }, [active])

  const handleMount: DiffOnMount = (editor) => {
    editorRef.current = editor
    // @monaco-editor/react reveals the editor after the wrapper leaves
    // display:none; force a layout so the diff is not stuck at 0x0.
    editor.layout()
    requestAnimationFrame(() => editor.layout())
  }

  const label = origPath ? `${origPath} → ${path}` : path
  // Monaco caches models by URI, so the scope must separate the staged and
  // working-tree diffs of the same file (they carry different content), and the
  // worktree so the same path in different worktrees does not collide.
  const scope = `${worktree ?? 'primary'}-${staged ? 'staged' : 'working'}`

  return (
    <div className="relative h-full w-full bg-[var(--editor)]">
      <div className="absolute inset-x-0 top-0 z-10 flex h-8 items-center gap-2 border-b border-[var(--border)] bg-[var(--editor-header)] px-3">
        <span className="truncate text-[12px] text-[var(--fg-2)]" title={label}>
          {label}
        </span>
        <span className="shrink-0 rounded bg-[var(--hover)] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[var(--muted-2)]">
          {staged ? t('ide.stagedDiff') : t('ide.workingDiff')}
        </span>
      </div>

      <div className="absolute inset-0 top-8">
        {loading && <p className="px-3 py-2 text-[13px] text-[var(--muted-2)]">{t('common.loading')}</p>}
        {!loading && error && <p className="px-3 py-2 text-[13px] text-[var(--danger)]">{error}</p>}
        {!loading && !error && ready && (
          <DiffEditor
            original={oldContent}
            modified={newContent}
            originalModelPath={`diff-original-${projectId}/${scope}/${origPath ?? path}`}
            modifiedModelPath={`diff-modified-${projectId}/${scope}/${path}`}
            theme={resolved === 'dark' ? 'vs-dark' : 'vs'}
            onMount={handleMount}
            loading={<p className="px-3 py-2 text-[13px] text-[var(--muted-2)]">{t('common.loading')}</p>}
            options={{
              fontSize: 13,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              renderSideBySide: true,
              readOnly: true,
            }}
          />
        )}
      </div>
    </div>
  )
}
