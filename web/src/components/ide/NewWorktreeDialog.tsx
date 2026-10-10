import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createWorktree,
  fetchBranches,
  type GitBranches,
  type Project,
  type Worktree,
} from '../../lib/api'
import { CloseIcon } from './icons'

const inputClass =
  'w-full rounded-lg border border-[var(--hover-strong)] bg-[var(--input)] px-3 py-2 text-sm text-[var(--fg)] outline-none transition placeholder:text-[var(--muted-3)] focus:border-indigo-500'
const labelClass = 'mb-1 block text-[12px] font-medium text-[var(--fg-3)]'

interface NewWorktreeDialogProps {
  project: Project
  onClose: () => void
  onCreated: (worktree: Worktree) => void
}

export function NewWorktreeDialog({ project, onClose, onCreated }: NewWorktreeDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [branch, setBranch] = useState('')
  const [createBranch, setCreateBranch] = useState(true)
  const [branches, setBranches] = useState<GitBranches | null>(null)
  const [branchesError, setBranchesError] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const firstFieldRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    firstFieldRef.current?.focus()
  }, [])

  useEffect(() => {
    let active = true
    fetchBranches(project.id)
      .then((result) => {
        if (active) setBranches(result)
      })
      .catch(() => {
        if (active) setBranchesError(true)
      })
    return () => {
      active = false
    }
  }, [project.id])

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
      const worktree = await createWorktree(project.id, {
        name: name.trim(),
        branch: branch.trim(),
        create_branch: createBranch,
      })
      onCreated(worktree)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiErrors.unknown'))
      setSubmitting(false)
    }
  }

  const canSubmit = name.trim().length > 0 && branch.trim().length > 0 && !submitting

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
        aria-labelledby="new-worktree-title"
        className="w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <h2 id="new-worktree-title" className="text-sm font-semibold text-[var(--fg-strong)]">
            {t('ide.newWorktreeDialog.title')}
          </h2>
          <button
            type="button"
            aria-label={t('ide.newWorktreeDialog.cancel')}
            disabled={submitting}
            onClick={onClose}
            className="rounded-md p-1 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:opacity-50"
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-4 py-4">
          {error && (
            <p
              role="alert"
              className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-[var(--danger)] ring-1 ring-red-500/30"
            >
              {error}
            </p>
          )}

          <div>
            <label htmlFor="worktree-name" className={labelClass}>
              {t('ide.newWorktreeDialog.name')}
            </label>
            <input
              id="worktree-name"
              ref={firstFieldRef}
              type="text"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('ide.newWorktreeDialog.namePlaceholder')}
              className={inputClass}
            />
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-[var(--fg-3)]">
            <input
              type="checkbox"
              checked={createBranch}
              onChange={(event) => {
                setCreateBranch(event.target.checked)
                setBranch('')
              }}
              className="h-3.5 w-3.5 accent-indigo-600"
            />
            {t('ide.newWorktreeDialog.createBranch')}
          </label>

          {createBranch ? (
            <div>
              <label htmlFor="worktree-branch" className={labelClass}>
                {t('ide.newWorktreeDialog.branch')}
              </label>
              <input
                id="worktree-branch"
                type="text"
                required
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                placeholder={t('ide.newWorktreeDialog.branchPlaceholder')}
                className={inputClass}
              />
            </div>
          ) : (
            <div>
              <label htmlFor="worktree-existing-branch" className={labelClass}>
                {t('ide.newWorktreeDialog.existingBranch')}
              </label>
              <select
                id="worktree-existing-branch"
                required
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                className={inputClass}
              >
                <option value="" disabled>
                  {t('ide.newWorktreeDialog.branch')}
                </option>
                {(branches?.branches ?? []).map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              {branchesError && (
                <p className="mt-1 text-xs text-[var(--danger)]">
                  {t('ide.newWorktreeDialog.branchesError')}
                </p>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              disabled={submitting}
              onClick={onClose}
              className="rounded-lg px-3 py-2 text-sm text-[var(--fg-3)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:opacity-50"
            >
              {t('ide.newWorktreeDialog.cancel')}
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting
                ? t('ide.newWorktreeDialog.submitting')
                : t('ide.newWorktreeDialog.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
