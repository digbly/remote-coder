import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { ChangedFile } from '../../lib/mock'
import {
  baseBranch,
  branch,
  stagedChanges,
  unstagedChanges,
} from '../../lib/mock'
import {
  BranchIcon,
  CheckIcon,
  ChevronDownIcon,
  CommitIcon,
  FileIcon,
  PrIcon,
  UndoIcon,
} from './icons'

function ChangeRow({ file }: { file: ChangedFile }) {
  return (
    <div className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] transition hover:bg-[#24262a]">
      <FileIcon width={14} height={14} className="shrink-0 text-[#7d828b]" />
      <span className="shrink-0 text-[#c8ccd4]">{file.name}</span>
      <span className="truncate text-[#6b7078]">{file.path}</span>
      <span className="ml-auto flex shrink-0 items-center gap-1.5 font-mono text-[11px]">
        <span className="text-[#6fbf8b]">+{file.added}</span>
        {file.removed > 0 && <span className="text-[#d98b94]">-{file.removed}</span>}
        <span className={file.status === 'A' ? 'text-[#6fbf8b]' : 'text-[#c9a24a]'}>
          {file.status}
        </span>
      </span>
    </div>
  )
}

function SectionHeader({
  title,
  count,
  action,
}: {
  title: string
  count: number
  action?: ReactNode
}) {
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#8b9099]">
      <ChevronDownIcon width={12} height={12} />
      <span>
        {title} {count}
      </span>
      <span className="ml-auto flex items-center gap-1">{action}</span>
    </div>
  )
}

export function RightPanel() {
  const { t } = useTranslation()

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-[#2c2e33] bg-[#1b1c1f] text-sm">
      <div className="flex items-center justify-between px-3.5 py-3">
        <span className="flex items-center gap-2 text-[13px] text-[#d7dae0]">
          <BranchIcon width={14} height={14} className="text-[#7d828b]" />
          {branch}
        </span>
        <span className="flex items-center gap-1 text-[11px] text-[#6b7078]">
          <span className="text-[#7d828b]">→</span>
          {baseBranch}
        </span>
      </div>

      <div className="px-3.5">
        <button
          type="button"
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-[13px] font-medium text-white transition hover:bg-indigo-500"
        >
          <PrIcon width={15} height={15} />
          {t('ide.createPr')}
        </button>
      </div>

      <div className="px-3.5 pt-3">
        <textarea
          rows={3}
          aria-label={t('ide.message')}
          placeholder={t('ide.message')}
          className="w-full resize-none rounded-lg border border-[#2c2e33] bg-[#141517] px-3 py-2 text-[12.5px] text-[#e6e8ec] outline-none transition placeholder:text-[#5a5f67] focus:border-indigo-500"
        />
        <button
          type="button"
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg border border-[#2c2e33] bg-[#232529] px-3 py-2 text-[13px] font-medium text-[#c2c6cc] transition hover:bg-[#2a2c30] hover:text-white"
        >
          <CheckIcon width={14} height={14} />
          {t('ide.commit')}
        </button>
      </div>

      <div className="mt-3 flex-1 overflow-y-auto px-1.5">
        <SectionHeader
          title={t('ide.changes')}
          count={unstagedChanges.length}
          action={
            <>
              <button type="button" className="rounded p-0.5 hover:bg-[#2a2c30] hover:text-white">
                <UndoIcon width={13} height={13} />
              </button>
              <button type="button" className="rounded p-0.5 hover:bg-[#2a2c30] hover:text-white">
                <CommitIcon width={13} height={13} />
              </button>
              <button type="button" className="rounded px-1 text-[10px] normal-case hover:bg-[#2a2c30] hover:text-white">
                {t('ide.viewAll')}
              </button>
            </>
          }
        />
        <div className="space-y-0.5">
          {unstagedChanges.map((file) => (
            <ChangeRow key={`${file.path}/${file.name}`} file={file} />
          ))}
        </div>

        <div className="mt-4">
          <SectionHeader
            title={t('ide.stagedChanges')}
            count={stagedChanges.length}
            action={
              <button type="button" className="rounded px-1 text-[10px] normal-case hover:bg-[#2a2c30] hover:text-white">
                {t('ide.viewAll')}
              </button>
            }
          />
          <div className="space-y-0.5">
            {stagedChanges.map((file) => (
              <ChangeRow key={`${file.path}/${file.name}`} file={file} />
            ))}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1.5 border-t border-[#2c2e33] px-2.5 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#8b9099]">
        <ChevronDownIcon width={12} height={12} />
        {t('ide.commits')}
      </div>
    </aside>
  )
}
