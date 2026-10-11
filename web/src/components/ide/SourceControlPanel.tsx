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
  DiscardIcon,
  GitFileIcon,
  MinusIcon,
  PlusIcon,
  PrIcon,
  RefreshIcon,
  SparklesIcon,
  SpinnerIcon,
} from './icons'
import { BranchMenu } from './BranchMenu'
import { gitStatusColor, GIT_STATUS_REFRESH_INTERVAL_MS } from './gitStatus'

function PathRow({
  label,
  status,
  action,
  onOpen,
}: {
  label: string
  status?: string
  action?: ReactNode
  onOpen?: () => void
}) {
  const content = (
    <>
      <GitFileIcon width={14} height={14} className="shrink-0 text-[var(--muted-2)]" />
      <span className="truncate text-[var(--fg-3-alt)]" title={label}>
        {label}
      </span>
    </>
  )
  return (
    <div className="group flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] transition hover:bg-[var(--hover-subtle)]">
      {onOpen ? (
        <button
          type="button"
          onClick={onOpen}
          title={label}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {content}
        </button>
      ) : (
        <span className="flex min-w-0 flex-1 items-center gap-2">{content}</span>
      )}
      <span className="ml-auto flex shrink-0 items-center gap-1.5">
        {status && (
          <span className={`font-mono text-[11px] ${gitStatusColor(status)}`}>{status}</span>
        )}
        {action}
      </span>
    </div>
  )
}

function ChangeRow({
  file,
  action,
  onOpen,
}: {
  file: GitChange
  action?: ReactNode
  onOpen?: () => void
}) {
  const label = file.orig_path ? `${file.orig_path} → ${file.path}` : file.path
  return <PathRow label={label} status={file.status} action={action} onOpen={onOpen} />
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
      <div className="group flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
        <ChevronDownIcon width={12} height={12} />
        <span>
          {title} {count}
        </span>
        {action && (
          <span className="ml-auto flex items-center gap-0.5 opacity-0 transition focus-within:opacity-100 group-hover:opacity-100">
            {action}
          </span>
        )}
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
  onOpenDiff: (path: string, staged: boolean, origPath?: string | null) => void
}

export function SourceControlPanel({ projectId, onOpenDiff }: SourceControlPanelProps) {
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

  function confirmDiscard(paths: string[]) {
    if (paths.length === 0 || !window.confirm(t('ide.discardConfirm'))) return
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
            {status.conflicted.length > 0 && (
              <Section title={t('ide.conflicts')} count={status.conflicted.length}>
                {status.conflicted.map((path) => (
                  <PathRow
                    key={path}
                    label={path}
                    status="U"
                    onOpen={() => onOpenDiff(path, false, null)}
                  />
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
                    <MinusIcon width={14} height={14} />
                  </RowAction>
                }
              >
                {status.staged.map((file) => (
                  <ChangeRow
                    key={`staged:${file.path}`}
                    file={file}
                    onOpen={() => onOpenDiff(file.path, true, file.orig_path)}
                    action={
                      <>
                        <RowAction
                          label={t('ide.discard')}
                          disabled={disabled}
                          onClick={() => handleDiscard(discardTargets(file))}
                        >
                          <DiscardIcon width={14} height={14} />
                        </RowAction>
                        <RowAction
                          label={t('ide.unstage')}
                          disabled={disabled}
                          onClick={() => handleUnstage([file.path])}
                        >
                          <MinusIcon width={14} height={14} />
                        </RowAction>
                      </>
                    }
                  />
                ))}
              </Section>
            )}
            {status.unstaged.length > 0 && (
              <Section
                title={t('ide.changes')}
                count={status.unstaged.length}
                action={
                  <>
                    <RowAction
                      label={t('ide.discardAll')}
                      disabled={disabled}
                      onClick={() => confirmDiscard(status.unstaged.flatMap(discardTargets))}
                    >
                      <DiscardIcon width={14} height={14} />
                    </RowAction>
                    <RowAction
                      label={t('ide.stageAll')}
                      disabled={disabled}
                      onClick={() => handleStage(status.unstaged.map((file) => file.path))}
                    >
                      <PlusIcon width={14} height={14} />
                    </RowAction>
                  </>
                }
              >
                {status.unstaged.map((file) => (
                  <ChangeRow
                    key={`unstaged:${file.path}`}
                    file={file}
                    onOpen={() => onOpenDiff(file.path, false, file.orig_path)}
                    action={
                      <>
                        <RowAction
                          label={t('ide.discard')}
                          disabled={disabled}
                          onClick={() => handleDiscard(discardTargets(file))}
                        >
                          <DiscardIcon width={14} height={14} />
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
              <Section
                title={t('ide.untracked')}
                count={status.untracked.length}
                action={
                  <>
                    <RowAction
                      label={t('ide.discardAll')}
                      disabled={disabled}
                      onClick={() => confirmDiscard(status.untracked)}
                    >
                      <DiscardIcon width={14} height={14} />
                    </RowAction>
                    <RowAction
                      label={t('ide.stageAll')}
                      disabled={disabled}
                      onClick={() => handleStage(status.untracked)}
                    >
                      <PlusIcon width={14} height={14} />
                    </RowAction>
                  </>
                }
              >
                {status.untracked.map((path) => (
                  <PathRow
                    key={`untracked:${path}`}
                    label={path}
                    status="?"
                    onOpen={() => onOpenDiff(path, false, null)}
                    action={
                      <>
                        <RowAction
                          label={t('ide.discard')}
                          disabled={disabled}
                          onClick={() => handleDiscard([path])}
                        >
                          <DiscardIcon width={14} height={14} />
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
