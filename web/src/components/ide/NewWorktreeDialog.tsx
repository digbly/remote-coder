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

type Tab = 'name' | 'branch'

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
  const [tab, setTab] = useState<Tab>('name')
  const [name, setName] = useState('')
  const [branch, setBranch] = useState('')
  const [branches, setBranches] = useState<GitBranches | null>(null)
  const [branchesError, setBranchesError] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)
  const branchRef = useRef<HTMLSelectElement>(null)

  useEffect(() => {
    if (tab === 'name') nameRef.current?.focus()
    else branchRef.current?.focus()
  }, [tab])

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
      const payload =
        tab === 'name'
          ? { name: name.trim(), branch: name.trim(), create_branch: true }
          : {
              name: branch.trim().replaceAll('/', '-'),
              branch: branch.trim(),
              create_branch: false,
            }
      const worktree = await createWorktree(project.id, payload)
      onCreated(worktree)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiErrors.unknown'))
      setSubmitting(false)
    }
  }

  const canSubmit =
    (tab === 'name' ? name.trim().length > 0 : branch.trim().length > 0) && !submitting

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

        <div className="flex gap-1 px-4 pt-3">
          {(['name', 'branch'] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => switchTab(value)}
              className={`rounded-md px-3 py-1.5 text-[13px] transition ${
                tab === value
                  ? 'bg-[var(--hover)] text-[var(--fg-strong)]'
                  : 'text-[var(--text-2)] hover:bg-[var(--hover-subtle)] hover:text-[var(--fg-strong)]'
              }`}
            >
              {value === 'name'
                ? t('ide.newWorktreeDialog.nameTab')
                : t('ide.newWorktreeDialog.branchTab')}
            </button>
          ))}
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

          {tab === 'name' ? (
            <div>
              <label htmlFor="worktree-name" className={labelClass}>
                {t('ide.newWorktreeDialog.name')}
              </label>
              <input
                id="worktree-name"
                ref={nameRef}
                type="text"
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t('ide.newWorktreeDialog.namePlaceholder')}
                className={inputClass}
              />
              <p className="mt-1 text-xs text-[var(--muted-3)]">
                {t('ide.newWorktreeDialog.nameHint')}
              </p>
            </div>
          ) : (
            <div>
              <label htmlFor="worktree-branch" className={labelClass}>
                {t('ide.newWorktreeDialog.branch')}
              </label>
              <select
                id="worktree-branch"
                ref={branchRef}
                required
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                className={inputClass}
              >
                <option value="" disabled>
                  {t('ide.newWorktreeDialog.branchPlaceholder')}
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
