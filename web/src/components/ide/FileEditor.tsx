import { useCallback, useEffect, useRef, useState } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import { useTranslation } from 'react-i18next'
import { fetchFileContent, saveFileContent } from '../../lib/api'
import { ensureMonaco } from '../../lib/monaco'
import { useTheme } from '../../lib/themeContext'

interface FileEditorProps {
  projectId: number
  path: string
  line?: number
  active: boolean
}

type EditorInstance = Parameters<OnMount>[0]

function revealLine(editor: EditorInstance, line: number): void {
  const model = editor.getModel()
  const target = model ? Math.min(line, model.getLineCount()) : line
  editor.setPosition({ lineNumber: target, column: 1 })
  editor.revealLineInCenter(target)
  editor.focus()
}

export function FileEditor({ projectId, path, line, active }: FileEditorProps) {
  const { t } = useTranslation()
  const { resolved } = useTheme()
  const [content, setContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [ready, setReady] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const containerRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const revealedLineRef = useRef<number | undefined>(undefined)
  const contentRef = useRef('')
  const savedRef = useRef('')
  const savingRef = useRef(false)
  const saveRef = useRef<() => void>(() => {})

  const dirty = content !== savedContent

  useEffect(() => {
    let disposed = false
    Promise.all([fetchFileContent(projectId, path), ensureMonaco()])
      .then(([file]) => {
        if (disposed) return
        contentRef.current = file.content
        savedRef.current = file.content
        setContent(file.content)
        setSavedContent(file.content)
        setReady(true)
      })
      .catch((err: unknown) => {
        if (!disposed) setLoadError(err instanceof Error ? err.message : t('ide.fileOpenFailed'))
      })
      .finally(() => {
        if (!disposed) setLoading(false)
      })
    return () => {
      disposed = true
    }
  }, [projectId, path, t])

  const save = useCallback(async () => {
    const snapshot = contentRef.current
    if (savingRef.current || snapshot === savedRef.current) return
    savingRef.current = true
    setSaving(true)
    try {
      await saveFileContent(projectId, path, snapshot)
      savedRef.current = snapshot
      setSavedContent(snapshot)
      setSaveError(null)
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : t('ide.saveFailed'))
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }, [projectId, path, t])

  useEffect(() => {
    saveRef.current = () => {
      void save()
    }
  }, [save])

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor
    // @monaco-editor/react creates the editor inside a display:none wrapper and
    // only reveals it afterwards. With automaticLayout disabled the editor keeps
    // its 0x0 measurement until the next layout() call (e.g. a tab switch), so
    // force a layout once the container is actually visible.
    editor.layout()
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => saveRef.current())
    if (active && line !== undefined) {
      revealedLineRef.current = line
      revealLine(editor, line)
    }
  }

  useEffect(() => {
    if (active) editorRef.current?.layout()
  }, [active])

  useEffect(() => {
    const editor = editorRef.current
    if (!active || !ready || line === undefined || !editor) return
    if (revealedLineRef.current === line) return
    revealedLineRef.current = line
    revealLine(editor, line)
  }, [active, ready, line])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver(() => editorRef.current?.layout())
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="flex h-full w-full flex-col bg-[var(--editor)]">
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--border)] bg-[var(--editor-header)] px-3 py-1.5">
        <span className="truncate text-[12px] text-[var(--fg-2)]" title={path}>
          {path}
        </span>
        {dirty && <span className="h-2 w-2 shrink-0 rounded-full bg-indigo-400" />}
        <div className="ml-auto flex items-center gap-2">
          {saveError && (
            <span className="max-w-[40%] truncate text-[11px] text-[var(--danger)]">{saveError}</span>
          )}
          <button
            type="button"
            onClick={() => void save()}
            disabled={!dirty || saving}
            className="rounded bg-[var(--hover)] px-2 py-0.5 text-[11px] text-[var(--fg-2)] transition hover:bg-[var(--hover-strong)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? t('ide.saving') : t('ide.save')}
          </button>
        </div>
      </div>

      <div ref={containerRef} className="relative min-h-0 flex-1">
        {loading && <p className="px-3 py-2 text-[13px] text-[var(--muted-2)]">{t('common.loading')}</p>}
        {!loading && loadError && (
          <p className="px-3 py-2 text-[13px] text-[var(--danger)]">{loadError}</p>
        )}
        {!loading && !loadError && ready && (
          <Editor
            path={`project-${projectId}/${path}`}
            value={content}
            theme={resolved === 'dark' ? 'vs-dark' : 'vs'}
            onChange={(value) => {
              const next = value ?? ''
              contentRef.current = next
              setContent(next)
            }}
            onMount={handleMount}
            loading={<p className="px-3 py-2 text-[13px] text-[var(--muted-2)]">{t('common.loading')}</p>}
            options={{
              fontSize: 13,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: false,
              tabSize: 2,
            }}
          />
        )}
      </div>
    </div>
  )
}
