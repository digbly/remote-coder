import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { GitBranches } from '../../lib/api'
import { BranchIcon, BranchPlusIcon, CheckIcon } from './icons'

interface BranchMenuProps {
  branches: GitBranches | null
  current: string | null
  disabled: boolean
  onSwitch: (name: string) => void
  onCreate: (name: string) => void
}

export function BranchMenu({ branches, current, disabled, onSwitch, onCreate }: BranchMenuProps) {
  const { t } = useTranslation()
  const [newBranch, setNewBranch] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const name = newBranch.trim()
    if (!name) return
    onCreate(name)
    setNewBranch('')
  }

  return (
    <div className="border-y border-[var(--border)] bg-[var(--surface-inset)] px-1.5 py-2">
      <p className="px-1.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
        {t('ide.branches')}
      </p>
      <div className="max-h-48 space-y-0.5 overflow-y-auto">
        {(branches?.branches ?? []).map((name) => (
          <button
            key={name}
            type="button"
            disabled={disabled}
            onClick={() => onSwitch(name)}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12.5px] text-[var(--fg-3-alt)] transition hover:bg-[var(--hover-subtle)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <BranchIcon width={13} height={13} className="shrink-0 text-[var(--muted-2)]" />
            <span className="truncate">{name}</span>
            {name === current && (
              <CheckIcon width={13} height={13} className="ml-auto shrink-0 text-[var(--success)]" />
            )}
          </button>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="mt-2 flex items-center gap-1.5 px-1.5">
        <input
          value={newBranch}
          onChange={(event) => setNewBranch(event.target.value)}
          placeholder={t('ide.newBranchPlaceholder')}
          aria-label={t('ide.createBranch')}
          className="min-w-0 flex-1 rounded-md border border-[var(--hover-strong-alt)] bg-[var(--input)] px-2.5 py-1.5 text-[12.5px] text-[var(--fg)] placeholder:text-[var(--muted-3)] focus:border-[var(--accent)] focus:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || newBranch.trim().length === 0}
          title={t('ide.createBranch')}
          aria-label={t('ide.createBranch')}
          className="rounded-md border border-[var(--border-strong)] bg-[var(--btn)] p-1.5 text-[var(--fg)] transition hover:bg-[var(--hover-alt)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <BranchPlusIcon width={14} height={14} />
        </button>
      </form>
    </div>
  )
}
