import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { deleteProject, type Project } from '../../lib/api'
import { CloseIcon } from './icons'

interface DeleteProjectDialogProps {
  project: Project
  onClose: () => void
  onDeleted: () => void
}

export function DeleteProjectDialog({ project, onClose, onDeleted }: DeleteProjectDialogProps) {
  const { t } = useTranslation()
  const managedClone = project.source === 'github'
  const [deleteFiles, setDeleteFiles] = useState(managedClone)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !submitting) onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, submitting])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      await deleteProject(project.id, deleteFiles)
      onDeleted()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiErrors.unknown'))
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/60 sm:items-center sm:justify-center sm:p-4"
      onClick={() => {
        if (!submitting) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-project-title"
        className="flex h-full w-full flex-col overflow-hidden border-[var(--border)] bg-[var(--surface)] pt-[var(--safe-top)] sm:h-auto sm:max-h-[90vh] sm:max-w-md sm:rounded-xl sm:shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <h2 id="delete-project-title" className="text-sm font-semibold text-[var(--fg-strong)]">
            {t('ide.deleteProjectDialog.title')}
          </h2>
          <button
            type="button"
            aria-label={t('ide.deleteProjectDialog.cancel')}
            disabled={submitting}
            onClick={onClose}
            className="rounded-md p-1 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:opacity-50"
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4 pb-[calc(1rem+var(--safe-bottom))]">
          {error && (
            <p
              role="alert"
              className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-[var(--danger)] ring-1 ring-red-500/30"
            >
              {error}
            </p>
          )}

          <p className="text-sm text-[var(--fg-2)]">
            {t('ide.deleteProjectConfirm', { name: project.name })}
          </p>

          {managedClone ? (
            <p className="break-all text-xs text-[var(--muted-3)]">
              {t('ide.deleteProjectDialog.deleteFilesHint', { path: project.path })}
            </p>
          ) : (
            <label className="flex items-start gap-2.5 text-sm text-[var(--fg-2)]">
              <input
                type="checkbox"
                checked={deleteFiles}
                disabled={submitting}
                onChange={(event) => setDeleteFiles(event.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 accent-red-500"
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-[var(--fg)]">{t('ide.deleteProjectDialog.deleteFiles')}</span>
                {deleteFiles && (
                  <span className="break-all text-xs text-[var(--muted-3)]">
                    {t('ide.deleteProjectDialog.deleteFilesHint', { path: project.path })}
                  </span>
                )}
              </span>
            </label>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              disabled={submitting}
              onClick={onClose}
              className="rounded-lg px-3 py-2 text-sm text-[var(--fg-3)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:opacity-50"
            >
              {t('ide.deleteProjectDialog.cancel')}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting
                ? t('ide.deleteProjectDialog.deleting')
                : t('ide.deleteProjectDialog.confirm')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
