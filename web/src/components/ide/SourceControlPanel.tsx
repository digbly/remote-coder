import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { fetchGitStatus, type GitChange, type GitStatus } from '../../lib/api'
import { BranchIcon, ChevronDownIcon, FileIcon, RefreshIcon } from './icons'

const REFRESH_INTERVAL_MS = 5000

const STATUS_COLORS: Record<string, string> = {
  A: 'text-[#6fbf8b]',
  M: 'text-[#c9a24a]',
  D: 'text-[#d98b94]',
  R: 'text-[#8ab4f8]',
  C: 'text-[#8ab4f8]',
  U: 'text-[#d98b94]',
}

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? 'text-[#8b9099]'
}

function PathRow({ label, status }: { label: string; status?: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] transition hover:bg-[#24262a]">
      <FileIcon width={14} height={14} className="shrink-0 text-[#7d828b]" />
      <span className="truncate text-[#c8ccd4]" title={label}>
        {label}
      </span>
      {status && (
        <span className={`ml-auto shrink-0 font-mono text-[11px] ${statusColor(status)}`}>
          {status}
        </span>
      )}
    </div>
  )
}

function ChangeRow({ file }: { file: GitChange }) {
  const label = file.orig_path ? `${file.orig_path} → ${file.path}` : file.path
  return <PathRow label={label} status={file.status} />
}

function Section({
  title,
  count,
  children,
}: {
  title: string
  count: number
  children: ReactNode
}) {
  return (
    <div className="mt-3">
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#8b9099]">
        <ChevronDownIcon width={12} height={12} />
        <span>
          {title} {count}
        </span>
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  )
}

export function SourceControlPanel({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<GitStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  useEffect(() => {
    let active = true
    fetchGitStatus(projectId)
      .then((next) => {
        if (!active) return
        setStatus(next)
        setError(null)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : t('ide.gitStatusError'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    const timer = window.setInterval(reload, REFRESH_INTERVAL_MS)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [projectId, t, reloadToken, reload])

  const clean =
    status !== null &&
    status.staged.length === 0 &&
    status.unstaged.length === 0 &&
    status.untracked.length === 0 &&
    status.conflicted.length === 0

  return (
    <aside
      aria-label={t('ide.sourceControl')}
      className="flex w-80 shrink-0 flex-col border-l border-[#2c2e33] bg-[#1b1c1f] text-sm"
    >
      <div className="flex items-center justify-between px-3.5 py-3">
        <span className="flex min-w-0 items-center gap-2 text-[13px] text-[#d7dae0]">
          <BranchIcon width={14} height={14} className="shrink-0 text-[#7d828b]" />
          <span className="truncate">{status?.branch ?? t('ide.sourceControl')}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {status?.upstream && (status.ahead > 0 || status.behind > 0) && (
            <span className="flex items-center gap-1 text-[11px] text-[#6b7078]">
              {status.ahead > 0 && <span>↑{status.ahead}</span>}
              {status.behind > 0 && <span>↓{status.behind}</span>}
            </span>
          )}
          <button
            type="button"
            aria-label={t('ide.refresh')}
            title={t('ide.refresh')}
            onClick={reload}
            className="rounded p-0.5 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
          >
            <RefreshIcon width={14} height={14} />
          </button>
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-1.5 pb-3">
        {loading && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#7d828b]">{t('common.loading')}</p>
        )}
        {!loading && error && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#f0a9b0]">{error}</p>
        )}
        {!loading && !error && clean && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#7d828b]">{t('ide.noChanges')}</p>
        )}
        {!loading && !error && status && !clean && (
          <>
            {status.conflicted.length > 0 && (
              <Section title={t('ide.conflicts')} count={status.conflicted.length}>
                {status.conflicted.map((path) => (
                  <PathRow key={path} label={path} status="U" />
                ))}
              </Section>
            )}
            {status.staged.length > 0 && (
              <Section title={t('ide.stagedChanges')} count={status.staged.length}>
                {status.staged.map((file) => (
                  <ChangeRow key={`staged:${file.path}`} file={file} />
                ))}
              </Section>
            )}
            {status.unstaged.length > 0 && (
              <Section title={t('ide.changes')} count={status.unstaged.length}>
                {status.unstaged.map((file) => (
                  <ChangeRow key={`unstaged:${file.path}`} file={file} />
                ))}
              </Section>
            )}
            {status.untracked.length > 0 && (
              <Section title={t('ide.untracked')} count={status.untracked.length}>
                {status.untracked.map((path) => (
                  <PathRow key={`untracked:${path}`} label={path} status="?" />
                ))}
              </Section>
            )}
          </>
        )}
      </div>
    </aside>
  )
}
