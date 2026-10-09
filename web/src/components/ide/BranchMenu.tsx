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
    <div className="border-y border-[#2c2e33] bg-[#17181b] px-1.5 py-2">
      <p className="px-1.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-[#8b9099]">
        {t('ide.branches')}
      </p>
      <div className="max-h-48 space-y-0.5 overflow-y-auto">
        {(branches?.branches ?? []).map((name) => (
          <button
            key={name}
            type="button"
            disabled={disabled}
            onClick={() => onSwitch(name)}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12.5px] text-[#c8ccd4] transition hover:bg-[#24262a] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <BranchIcon width={13} height={13} className="shrink-0 text-[#7d828b]" />
            <span className="truncate">{name}</span>
            {name === current && (
              <CheckIcon width={13} height={13} className="ml-auto shrink-0 text-[#6fbf8b]" />
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
          className="min-w-0 flex-1 rounded-md border border-[#33363c] bg-[#141517] px-2.5 py-1.5 text-[12.5px] text-[#e6e8ec] placeholder:text-[#6b7078] focus:border-[#4c8bf5] focus:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || newBranch.trim().length === 0}
          title={t('ide.createBranch')}
          aria-label={t('ide.createBranch')}
          className="rounded-md border border-[#3a3d43] bg-[#23252a] p-1.5 text-[#e6e8ec] transition hover:bg-[#2a2c32] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <BranchPlusIcon width={14} height={14} />
        </button>
      </form>
    </div>
  )
}
