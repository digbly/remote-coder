import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  commitChanges,
  createPullRequest,
  fetchGitStatus,
  stagePaths,
  unstagePaths,
  type GitChange,
  type GitStatus,
} from '../../lib/api'
import {
  BranchIcon,
  ChevronDownIcon,
  CommitIcon,
  FileIcon,
  PlusIcon,
  PrIcon,
  RefreshIcon,
  UndoIcon,
} from './icons'

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

function PathRow({
  label,
  status,
  action,
}: {
  label: string
  status?: string
  action?: ReactNode
}) {
  return (
    <div className="group flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] transition hover:bg-[#24262a]">
      <FileIcon width={14} height={14} className="shrink-0 text-[#7d828b]" />
      <span className="truncate text-[#c8ccd4]" title={label}>
        {label}
      </span>
      <span className="ml-auto flex shrink-0 items-center gap-1.5">
        {status && (
          <span className={`font-mono text-[11px] ${statusColor(status)}`}>{status}</span>
        )}
        {action}
      </span>
    </div>
  )
}

function ChangeRow({ file, action }: { file: GitChange; action?: ReactNode }) {
  const label = file.orig_path ? `${file.orig_path} → ${file.path}` : file.path
  return <PathRow label={label} status={file.status} action={action} />
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

function RowAction({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string
  onClick: () => void
  disabled: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="rounded p-0.5 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  )
}

export function SourceControlPanel({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<GitStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)
  const [message, setMessage] = useState('')
  const [branch, setBranch] = useState('')
  const [busy, setBusy] = useState<'stage' | 'commit' | 'pullRequest' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pullRequestUrl, setPullRequestUrl] = useState<string | null>(null)

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

  const canCommit = status !== null && status.staged.length > 0 && message.trim().length > 0
  const canOpenPullRequest = status !== null && branch.trim().length > 0

  function runAction(kind: 'stage' | 'commit' | 'pullRequest', action: () => Promise<void>) {
    setBusy(kind)
    setActionError(null)
    if (kind !== 'pullRequest') setPullRequestUrl(null)
    action()
      .catch((err) => {
        setActionError(err instanceof Error ? err.message : t('ide.stageFailed'))
      })
      .finally(() => {
        setBusy(null)
        reload()
      })
  }

  function handleStage(paths: string[]) {
    runAction('stage', async () => {
      setStatus(await stagePaths(projectId, paths))
    })
  }

  function handleUnstage(paths: string[]) {
    runAction('stage', async () => {
      setStatus(await unstagePaths(projectId, paths))
    })
  }

  function handleCommit(event: FormEvent) {
    event.preventDefault()
    if (!canCommit) return
    runAction('commit', async () => {
      await commitChanges(projectId, message.trim())
      setMessage('')
    })
  }

  function handleCreatePullRequest(event: FormEvent) {
    event.preventDefault()
    if (!canOpenPullRequest) return
    runAction('pullRequest', async () => {
      const result = await createPullRequest(projectId, branch.trim())
      setPullRequestUrl(result.url)
      setBranch('')
    })
  }

  const disabled = busy !== null

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
                  <ChangeRow
                    key={`staged:${file.path}`}
                    file={file}
                    action={
                      <RowAction
                        label={t('ide.unstage')}
                        disabled={disabled}
                        onClick={() => handleUnstage([file.path])}
                      >
                        <UndoIcon width={14} height={14} />
                      </RowAction>
                    }
                  />
                ))}
              </Section>
            )}
            {status.unstaged.length > 0 && (
              <Section title={t('ide.changes')} count={status.unstaged.length}>
                {status.unstaged.map((file) => (
                  <ChangeRow
                    key={`unstaged:${file.path}`}
                    file={file}
                    action={
                      <RowAction
                        label={t('ide.stage')}
                        disabled={disabled}
                        onClick={() => handleStage([file.path])}
                      >
                        <PlusIcon width={14} height={14} />
                      </RowAction>
                    }
                  />
                ))}
              </Section>
            )}
            {status.untracked.length > 0 && (
              <Section title={t('ide.untracked')} count={status.untracked.length}>
                {status.untracked.map((path) => (
                  <PathRow
                    key={`untracked:${path}`}
                    label={path}
                    status="?"
                    action={
                      <RowAction
                        label={t('ide.stage')}
                        disabled={disabled}
                        onClick={() => handleStage([path])}
                      >
                        <PlusIcon width={14} height={14} />
                      </RowAction>
                    }
                  />
                ))}
              </Section>
            )}
          </>
        )}
      </div>

      {!loading && !error && status && (
        <div className="border-t border-[#2c2e33]">
          <form onSubmit={handleCommit} className="space-y-2 p-2.5">
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={t('ide.commitMessagePlaceholder')}
              rows={2}
              className="w-full resize-none rounded-md border border-[#33363c] bg-[#141517] px-2.5 py-2 text-[12.5px] text-[#e6e8ec] placeholder:text-[#6b7078] focus:border-[#4c8bf5] focus:outline-none"
            />
            <button
              type="submit"
              disabled={disabled || !canCommit}
              className="flex w-full items-center justify-center gap-1.5 rounded-md bg-[#4c8bf5] px-3 py-1.5 text-[12.5px] font-medium text-white transition hover:bg-[#3f7ae0] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <CommitIcon width={14} height={14} />
              {busy === 'commit' ? t('ide.committing') : t('ide.commit')}
            </button>
          </form>

          <form onSubmit={handleCreatePullRequest} className="space-y-2 border-t border-[#2c2e33] p-2.5">
            <label className="block text-[11px] font-semibold uppercase tracking-wider text-[#8b9099]">
              {t('ide.branchName')}
            </label>
            <input
              value={branch}
              onChange={(event) => setBranch(event.target.value)}
              placeholder={status.branch ?? t('ide.branchNamePlaceholder')}
              className="w-full rounded-md border border-[#33363c] bg-[#141517] px-2.5 py-1.5 text-[12.5px] text-[#e6e8ec] placeholder:text-[#6b7078] focus:border-[#4c8bf5] focus:outline-none"
            />
            <p className="text-[11px] leading-snug text-[#6b7078]">{t('ide.prHint')}</p>
            <button
              type="submit"
              disabled={disabled || !canOpenPullRequest}
              className="flex w-full items-center justify-center gap-1.5 rounded-md border border-[#3a3d43] bg-[#23252a] px-3 py-1.5 text-[12.5px] font-medium text-[#e6e8ec] transition hover:bg-[#2a2c32] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <PrIcon width={14} height={14} />
              {busy === 'pullRequest' ? t('ide.creatingPr') : t('ide.createPr')}
            </button>
          </form>

          {actionError && (
            <p className="px-2.5 pb-2.5 text-[12px] text-[#f0a9b0]">{actionError}</p>
          )}
          {pullRequestUrl && (
            <a
              href={pullRequestUrl}
              target="_blank"
              rel="noreferrer"
              className="mx-2.5 mb-2.5 block truncate text-[12px] text-[#6fbf8b] hover:underline"
            >
              {t('ide.prCreated')} — {pullRequestUrl}
            </a>
          )}
        </div>
      )}
    </aside>
  )
}
