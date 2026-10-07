import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createGithubProject,
  createLocalProject,
  type Project,
} from '../../lib/api'
import { CloseIcon } from './icons'
import { FolderBrowserDialog } from './FolderBrowserDialog'

type Tab = 'local' | 'github'

const inputClass =
  'w-full rounded-lg border border-[#33363b] bg-[#141517] px-3 py-2 text-sm text-[#e6e8ec] outline-none transition placeholder:text-[#6b7078] focus:border-indigo-500'
const labelClass = 'mb-1 block text-[12px] font-medium text-[#c2c6cc]'

interface NewProjectDialogProps {
  onClose: () => void
  onCreated: (project: Project) => void
}

export function NewProjectDialog({ onClose, onCreated }: NewProjectDialogProps) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('local')
  const [path, setPath] = useState('')
  const [name, setName] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [token, setToken] = useState('')
  const [branch, setBranch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [showBrowser, setShowBrowser] = useState(false)
  const firstFieldRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    firstFieldRef.current?.focus()
  }, [tab])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !submitting && !showBrowser) onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, submitting, showBrowser])

  function switchTab(next: Tab) {
    setTab(next)
    setError(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const trimmedName = name.trim()
      const project =
        tab === 'local'
          ? await createLocalProject({
              path: path.trim(),
              ...(trimmedName ? { name: trimmedName } : {}),
            })
          : await createGithubProject({
              repo_url: repoUrl.trim(),
              ...(trimmedName ? { name: trimmedName } : {}),
              ...(token.trim() ? { token: token.trim() } : {}),
              ...(branch.trim() ? { branch: branch.trim() } : {}),
            })
      onCreated(project)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiErrors.unknown'))
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={() => {
        if (!submitting) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-title"
        className="w-full max-w-md rounded-xl border border-[#2c2e33] bg-[#1b1c1f] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[#2c2e33] px-4 py-3">
          <h2 id="new-project-title" className="text-sm font-semibold text-white">
            {t('ide.newProjectDialog.title')}
          </h2>
          <button
            type="button"
            aria-label={t('ide.newProjectDialog.cancel')}
            disabled={submitting}
            onClick={onClose}
            className="rounded-md p-1 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white disabled:opacity-50"
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>

        <div className="flex gap-1 px-4 pt-3">
          {(['local', 'github'] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => switchTab(value)}
              className={`rounded-md px-3 py-1.5 text-[13px] transition ${
                tab === value
                  ? 'bg-[#2a2c30] text-white'
                  : 'text-[#9aa0a8] hover:bg-[#24262a] hover:text-white'
              }`}
            >
              {value === 'local' ? t('ide.newProjectDialog.tabLocal') : t('ide.newProjectDialog.tabGithub')}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-4 py-4">
          {error && (
            <p
              role="alert"
              className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-[#f0a9b0] ring-1 ring-red-500/30"
            >
              {error}
            </p>
          )}

          {tab === 'local' ? (
            <div>
              <label htmlFor="project-path" className={labelClass}>
                {t('ide.newProjectDialog.path')}
              </label>
              <div className="flex gap-2">
                <input
                  id="project-path"
                  ref={firstFieldRef}
                  type="text"
                  required
                  value={path}
                  onChange={(event) => setPath(event.target.value)}
                  placeholder={t('ide.newProjectDialog.pathPlaceholder')}
                  className={inputClass}
                />
                <button
                  type="button"
                  onClick={() => setShowBrowser(true)}
                  className="shrink-0 rounded-lg border border-[#33363b] px-3 text-[13px] text-[#c2c6cc] transition hover:bg-[#2a2c30] hover:text-white"
                >
                  {t('ide.newProjectDialog.browse')}
                </button>
              </div>
            </div>
          ) : (
            <>
              <div>
                <label htmlFor="project-repo-url" className={labelClass}>
                  {t('ide.newProjectDialog.repoUrl')}
                </label>
                <input
                  id="project-repo-url"
                  ref={firstFieldRef}
                  type="text"
                  required
                  value={repoUrl}
                  onChange={(event) => setRepoUrl(event.target.value)}
                  placeholder={t('ide.newProjectDialog.repoUrlPlaceholder')}
                  className={inputClass}
                />
              </div>
              <div>
                <label htmlFor="project-token" className={labelClass}>
                  {t('ide.newProjectDialog.token')}
                </label>
                <input
                  id="project-token"
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder={t('ide.newProjectDialog.tokenPlaceholder')}
                  className={inputClass}
                />
              </div>
              <div>
                <label htmlFor="project-branch" className={labelClass}>
                  {t('ide.newProjectDialog.branch')}
                </label>
                <input
                  id="project-branch"
                  type="text"
                  value={branch}
                  onChange={(event) => setBranch(event.target.value)}
                  placeholder={t('ide.newProjectDialog.branchPlaceholder')}
                  className={inputClass}
                />
              </div>
            </>
          )}

          <div>
            <label htmlFor="project-name" className={labelClass}>
              {t('ide.newProjectDialog.name')}{' '}
              <span className="text-[#6b7078]">({t('ide.newProjectDialog.optional')})</span>
            </label>
            <input
              id="project-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('ide.newProjectDialog.namePlaceholder')}
              className={inputClass}
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              disabled={submitting}
              onClick={onClose}
              className="rounded-lg px-3 py-2 text-sm text-[#c2c6cc] transition hover:bg-[#2a2c30] hover:text-white disabled:opacity-50"
            >
              {t('ide.newProjectDialog.cancel')}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting
                ? t('ide.newProjectDialog.submitting')
                : t('ide.newProjectDialog.submit')}
            </button>
          </div>
        </form>
      </div>

      {showBrowser && (
        <FolderBrowserDialog
          initialPath={path.trim() || undefined}
          onClose={() => setShowBrowser(false)}
          onSelect={(selected) => {
            setPath(selected)
            setShowBrowser(false)
          }}
        />
      )}
    </div>
  )
}
