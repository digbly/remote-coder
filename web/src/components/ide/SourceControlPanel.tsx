import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  checkoutBranch,
  commitChanges,
  createBranch,
  createPullRequest,
  discardPaths,
  fetchBranches,
  fetchGitStatus,
  generateCommitMessage,
  pullBranch,
  pushBranch,
  stageAllPaths,
  stagePaths,
  unstageAllPaths,
  unstagePaths,
  type GitBranches,
  type GitChange,
  type GitStatus,
} from '../../lib/api'
import {
  BranchIcon,
  ChevronDownIcon,
  CloudDownloadIcon,
  CloudUploadIcon,
  CommitIcon,
  FileIcon,
  PlusIcon,
  PrIcon,
  RefreshIcon,
  SparklesIcon,
  SpinnerIcon,
  TrashIcon,
  UndoIcon,
} from './icons'
import { BranchMenu } from './BranchMenu'
import { gitStatusColor, GIT_STATUS_REFRESH_INTERVAL_MS } from './gitStatus'

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
    <div className="group flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] transition hover:bg-[var(--hover-subtle)]">
      <FileIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
      <span className="truncate text-[var(--fg-3-alt)]" title={label}>
        {label}
      </span>
      <span className="ml-auto flex shrink-0 items-center gap-1.5">
        {status && (
          <span className={`font-mono text-[11px] ${gitStatusColor(status)}`}>{status}</span>
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

function discardTargets(file: GitChange): string[] {
  return file.orig_path ? [file.orig_path, file.path] : [file.path]
}

function Section({
  title,
  count,
  action,
  children,
}: {
  title: string
  count: number
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="mt-3">
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
        <ChevronDownIcon width={12} height={12} />
        <span>
          {title} {count}
        </span>
        {action && <span className="ml-auto">{action}</span>}
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
      className="rounded p-0.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  )
}

function ToolbarButton({
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
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1.5 rounded-md border border-[var(--border-strong)] bg-[var(--btn)] px-2.5 py-1 text-[12px] font-medium text-[var(--fg-2)] transition hover:bg-[var(--hover-alt)] disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
      {label}
    </button>
  )
}

type BusyAction =
  | 'stage'
  | 'commit'
  | 'generate'
  | 'pullRequest'
  | 'discard'
  | 'push'
  | 'pull'
  | 'branch'

interface SourceControlPanelProps {
  projectId: number
}

export function SourceControlPanel({ projectId }: SourceControlPanelProps) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<GitStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)
  const [message, setMessage] = useState('')
  const [branch, setBranch] = useState('')
  const [busy, setBusy] = useState<BusyAction | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pullRequestUrl, setPullRequestUrl] = useState<string | null>(null)
  const [branchList, setBranchList] = useState<GitBranches | null>(null)
  const [branchMenuOpen, setBranchMenuOpen] = useState(false)

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
    const timer = window.setInterval(reload, GIT_STATUS_REFRESH_INTERVAL_MS)
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
  const canStageAll = status !== null && (status.unstaged.length > 0 || status.untracked.length > 0)
  const canDiscardAll =
    status !== null &&
    (status.staged.length > 0 || status.unstaged.length > 0 || status.untracked.length > 0)
  const canPull = status !== null && Boolean(status.upstream)

  function runAction(
    kind: BusyAction,
    action: () => Promise<void>,
    fallbackMessage: string,
  ) {
    setBusy(kind)
    setActionError(null)
    if (kind !== 'pullRequest') setPullRequestUrl(null)
    action()
      .catch((err) => {
        setActionError(err instanceof Error ? err.message : fallbackMessage)
      })
      .finally(() => {
        setBusy(null)
        reload()
      })
  }

  function handleStage(paths: string[]) {
    runAction(
      'stage',
      async () => {
        setStatus(await stagePaths(projectId, paths))
      },
      t('ide.stageFailed'),
    )
  }

  function handleUnstage(paths: string[]) {
    runAction(
      'stage',
      async () => {
        setStatus(await unstagePaths(projectId, paths))
      },
      t('ide.stageFailed'),
    )
  }

  function handleStageAll() {
    runAction(
      'stage',
      async () => {
        setStatus(await stageAllPaths(projectId))
      },
      t('ide.stageFailed'),
    )
  }

  function handleUnstageAll() {
    runAction(
      'stage',
      async () => {
        setStatus(await unstageAllPaths(projectId))
      },
      t('ide.stageFailed'),
    )
  }

  function handleDiscard(paths: string[]) {
    runAction(
      'discard',
      async () => {
        setStatus(await discardPaths(projectId, paths))
      },
      t('ide.discardFailed'),
    )
  }

  function handleDiscardAll() {
    if (!status || !window.confirm(t('ide.discardConfirm'))) return
    const paths = [
      ...status.staged.flatMap(discardTargets),
      ...status.unstaged.flatMap(discardTargets),
      ...status.untracked,
    ]
    handleDiscard(paths)
  }

  function handlePush() {
    runAction(
      'push',
      async () => {
        setStatus(await pushBranch(projectId))
      },
      t('ide.pushFailed'),
    )
  }

  function handlePull() {
    runAction(
      'pull',
      async () => {
        setStatus(await pullBranch(projectId))
      },
      t('ide.pullFailed'),
    )
  }

  function handleToggleBranchMenu() {
    const next = !branchMenuOpen
    setBranchMenuOpen(next)
    if (next) {
      fetchBranches(projectId)
        .then(setBranchList)
        .catch((err) => {
          setActionError(err instanceof Error ? err.message : t('ide.switchBranchFailed'))
        })
    }
  }

  function handleSwitchBranch(name: string) {
    if (name === status?.branch) {
      setBranchMenuOpen(false)
      return
    }
    runAction(
      'branch',
      async () => {
        setStatus(await checkoutBranch(projectId, name))
        setBranchMenuOpen(false)
      },
      t('ide.switchBranchFailed'),
    )
  }

  function handleCreateBranch(name: string) {
    runAction(
      'branch',
      async () => {
        setStatus(await createBranch(projectId, name))
        setBranchList(await fetchBranches(projectId))
        setBranchMenuOpen(false)
      },
      t('ide.createBranchFailed'),
    )
  }

  function handleCommit(event: FormEvent) {
    event.preventDefault()
    if (!canCommit) return
    runAction(
      'commit',
      async () => {
        await commitChanges(projectId, message.trim())
        setMessage('')
      },
      t('ide.commitFailed'),
    )
  }

  function handleGenerate() {
    runAction(
      'generate',
      async () => {
        const result = await generateCommitMessage(projectId)
        setMessage(result.message)
      },
      t('ide.generateCommitMessageFailed'),
    )
  }

  function handleCreatePullRequest(event: FormEvent) {
    event.preventDefault()
    if (!canOpenPullRequest) return
    runAction(
      'pullRequest',
      async () => {
        const result = await createPullRequest(projectId, branch.trim())
        setPullRequestUrl(result.url)
        setBranch('')
      },
      t('ide.prFailed'),
    )
  }

  const disabled = busy !== null

  return (
    <div className="flex min-h-0 flex-1 flex-col text-sm">
      <div className="flex items-center gap-1.5 px-3.5 py-3">
        <button
          type="button"
          onClick={handleToggleBranchMenu}
          aria-expanded={branchMenuOpen}
          title={t('ide.branches')}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-0.5 text-[13px] text-[var(--fg-2)] transition hover:bg-[var(--hover-subtle)]"
        >
          <BranchIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
          <span className="truncate">{status?.branch ?? t('ide.sourceControl')}</span>
          <ChevronDownIcon width={12} height={12} className="shrink-0 text-[var(--muted-2)]" />
        </button>
        <span className="flex shrink-0 items-center gap-1">
          {status?.upstream && (status.ahead > 0 || status.behind > 0) && (
            <span className="flex items-center gap-1 pr-0.5 text-[11px] text-[var(--muted-3)]">
              {status.ahead > 0 && <span>↑{status.ahead}</span>}
              {status.behind > 0 && <span>↓{status.behind}</span>}
            </span>
          )}
          <button
            type="button"
            aria-label={t('ide.pull')}
            title={t('ide.pull')}
            onClick={handlePull}
            disabled={disabled || !canPull}
            className="rounded p-0.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <CloudDownloadIcon width={14} height={14} />
          </button>
          <button
            type="button"
            aria-label={t('ide.push')}
            title={t('ide.push')}
            onClick={handlePush}
            disabled={disabled || status === null}
            className="rounded p-0.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <CloudUploadIcon width={14} height={14} />
          </button>
          <button
            type="button"
            aria-label={t('ide.refresh')}
            title={t('ide.refresh')}
            onClick={reload}
            className="rounded p-0.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
          >
            <RefreshIcon width={14} height={14} />
          </button>
        </span>
      </div>

      {branchMenuOpen && (
        <BranchMenu
          branches={branchList}
          current={status?.branch ?? null}
          disabled={disabled}
          onSwitch={handleSwitchBranch}
          onCreate={handleCreateBranch}
        />
      )}

      {!loading && !error && status && (
        <div className="border-b border-[var(--border)]">
          <form onSubmit={handleCommit} className="space-y-2 p-2.5">
            <div className="relative">
              <textarea
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder={t('ide.commitMessagePlaceholder')}
                aria-label={t('ide.commitMessagePlaceholder')}
                rows={2}
                className="w-full resize-none rounded-md border border-[var(--hover-strong-alt)] bg-[var(--input)] px-2.5 py-2 pr-8 text-[12.5px] text-[var(--fg)] placeholder:text-[var(--muted-3)] focus:border-[var(--accent)] focus:outline-none"
              />
              <button
                type="button"
                onClick={handleGenerate}
                disabled={disabled || clean}
                aria-label={t('ide.generateCommitMessage')}
                aria-busy={busy === 'generate'}
                title={
                  busy === 'generate'
                    ? t('ide.generatingCommitMessage')
                    : t('ide.generateCommitMessage')
                }
                className="absolute right-1.5 top-1.5 cursor-pointer rounded p-0.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy === 'generate' ? (
                  <SpinnerIcon width={14} height={14} className="animate-spin" />
                ) : (
                  <SparklesIcon width={14} height={14} />
                )}
              </button>
            </div>
            <button
              type="submit"
              disabled={disabled || !canCommit}
              className="flex w-full items-center justify-center gap-1.5 rounded-md bg-[var(--accent)] px-3 py-1.5 text-[12.5px] font-medium text-white transition hover:bg-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <CommitIcon width={14} height={14} />
              {busy === 'commit' ? t('ide.committing') : t('ide.commit')}
            </button>
          </form>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-1.5 pb-3">
        {loading && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">{t('common.loading')}</p>
        )}
        {!loading && error && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--danger)]">{error}</p>
        )}
        {!loading && !error && clean && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">{t('ide.noChanges')}</p>
        )}
        {!loading && !error && status && !clean && (
          <>
            <div className="flex items-center gap-2 px-1.5 pt-1.5">
              <ToolbarButton
                label={t('ide.stageAll')}
                onClick={handleStageAll}
                disabled={disabled || !canStageAll}
              >
                <PlusIcon width={14} height={14} />
              </ToolbarButton>
              <ToolbarButton
                label={t('ide.discardAll')}
                onClick={handleDiscardAll}
                disabled={disabled || !canDiscardAll}
              >
                <TrashIcon width={14} height={14} />
              </ToolbarButton>
            </div>
            {status.conflicted.length > 0 && (
              <Section title={t('ide.conflicts')} count={status.conflicted.length}>
                {status.conflicted.map((path) => (
                  <PathRow key={path} label={path} status="U" />
                ))}
              </Section>
            )}
            {status.staged.length > 0 && (
              <Section
                title={t('ide.stagedChanges')}
                count={status.staged.length}
                action={
                  <RowAction
                    label={t('ide.unstageAll')}
                    disabled={disabled}
                    onClick={handleUnstageAll}
                  >
                    <UndoIcon width={14} height={14} />
                  </RowAction>
                }
              >
                {status.staged.map((file) => (
                  <ChangeRow
                    key={`staged:${file.path}`}
                    file={file}
                    action={
                      <>
                        <RowAction
                          label={t('ide.discard')}
                          disabled={disabled}
                          onClick={() => handleDiscard(discardTargets(file))}
                        >
                          <TrashIcon width={14} height={14} />
                        </RowAction>
                        <RowAction
                          label={t('ide.unstage')}
                          disabled={disabled}
                          onClick={() => handleUnstage([file.path])}
                        >
                          <UndoIcon width={14} height={14} />
                        </RowAction>
                      </>
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
                      <>
                        <RowAction
                          label={t('ide.discard')}
                          disabled={disabled}
                          onClick={() => handleDiscard(discardTargets(file))}
                        >
                          <TrashIcon width={14} height={14} />
                        </RowAction>
                        <RowAction
                          label={t('ide.stage')}
                          disabled={disabled}
                          onClick={() => handleStage([file.path])}
                        >
                          <PlusIcon width={14} height={14} />
                        </RowAction>
                      </>
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
                      <>
                        <RowAction
                          label={t('ide.discard')}
                          disabled={disabled}
                          onClick={() => handleDiscard([path])}
                        >
                          <TrashIcon width={14} height={14} />
                        </RowAction>
                        <RowAction
                          label={t('ide.stage')}
                          disabled={disabled}
                          onClick={() => handleStage([path])}
                        >
                          <PlusIcon width={14} height={14} />
                        </RowAction>
                      </>
                    }
                  />
                ))}
              </Section>
            )}
          </>
        )}
      </div>

      {!loading && !error && status && (
        <div className="border-t border-[var(--border)]">
          <form onSubmit={handleCreatePullRequest} className="space-y-2 p-2.5">
            <label
              htmlFor="git-pr-branch"
              className="block text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]"
            >
              {t('ide.branchName')}
            </label>
            <input
              id="git-pr-branch"
              value={branch}
              onChange={(event) => setBranch(event.target.value)}
              placeholder={t('ide.branchNamePlaceholder')}
              className="w-full rounded-md border border-[var(--hover-strong-alt)] bg-[var(--input)] px-2.5 py-1.5 text-[12.5px] text-[var(--fg)] placeholder:text-[var(--muted-3)] focus:border-[var(--accent)] focus:outline-none"
            />
            <p className="text-[11px] leading-snug text-[var(--muted-3)]">{t('ide.prHint')}</p>
            <button
              type="submit"
              disabled={disabled || !canOpenPullRequest}
              className="flex w-full items-center justify-center gap-1.5 rounded-md border border-[var(--border-strong)] bg-[var(--btn)] px-3 py-1.5 text-[12.5px] font-medium text-[var(--fg)] transition hover:bg-[var(--hover-alt)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <PrIcon width={14} height={14} />
              {busy === 'pullRequest' ? t('ide.creatingPr') : t('ide.createPr')}
            </button>
          </form>

          {actionError && (
            <p className="px-2.5 pb-2.5 text-[12px] text-[var(--danger)]">{actionError}</p>
          )}
          {pullRequestUrl && (
            <a
              href={pullRequestUrl}
              target="_blank"
              rel="noreferrer"
              className="mx-2.5 mb-2.5 block truncate text-[12px] text-[var(--success)] hover:underline"
            >
              {t('ide.prCreated')} — {pullRequestUrl}
            </a>
          )}
        </div>
      )}
    </div>
  )
}
