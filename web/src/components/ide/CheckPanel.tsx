import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createBranch,
  createPullRequest,
  deleteWorktree,
  fetchCurrentPullRequest,
  mergePullRequest,
  type GitPullRequestSummary,
} from '../../lib/api'
import { refreshProjectWorktrees } from '../../lib/projectCache'
import { useConfirm } from '../../lib/confirmContext'
import { useAsyncData } from '../../lib/useAsyncData'
import { BranchIcon, PrIcon, RefreshIcon, SpinnerIcon, TrashIcon } from './icons'

const STATE_COLORS: Record<string, string> = {
  OPEN: 'text-[var(--success)]',
  MERGED: 'text-[var(--info)]',
  CLOSED: 'text-[var(--danger-2)]',
}

function stateColor(state: string): string {
  return STATE_COLORS[state.toUpperCase()] ?? 'text-[var(--muted)]'
}

function PullRequestCard({ pullRequest }: { pullRequest: GitPullRequestSummary }) {
  const { t } = useTranslation()
  return (
    <div className="mx-1.5 mt-2 rounded-md border border-[var(--border)] bg-[var(--surface-2)] p-3">
      <div className="flex items-start gap-2">
        <PrIcon width={15} height={15} className="mt-0.5 shrink-0 text-[var(--muted-2)]" />
        <div className="min-w-0 flex-1">
          <a
            href={pullRequest.url}
            target="_blank"
            rel="noreferrer"
            className="block truncate text-[13px] font-medium text-[var(--fg)] hover:underline"
            title={pullRequest.title}
          >
            {pullRequest.title}
          </a>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
            <span className="text-[var(--muted-2)]">#{pullRequest.number}</span>
            <span className={`font-medium ${stateColor(pullRequest.state)}`}>
              {pullRequest.state.toLowerCase()}
            </span>
            {pullRequest.is_draft && (
              <span className="rounded border border-[var(--border-strong-alt)] px-1.5 py-px text-[10px] text-[var(--muted)]">
                {t('ide.draft')}
              </span>
            )}
          </div>
          {pullRequest.head && pullRequest.base && (
            <p className="mt-1.5 truncate font-mono text-[11px] text-[var(--muted)]">
              {pullRequest.head} → {pullRequest.base}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

type BusyAction = 'create' | 'merge' | 'delete' | 'branch'

const BUTTON_TONES = {
  primary: 'bg-indigo-600 text-white hover:bg-indigo-500',
  merge: 'bg-emerald-600 text-white hover:bg-emerald-500',
  danger: 'border border-[var(--danger)]/40 text-[var(--danger)] hover:bg-red-500/10',
} as const

function ActionButton({
  kind,
  busy,
  icon,
  label,
  busyLabel,
  tone,
  submit = false,
  disabled = false,
  onClick,
}: {
  kind: BusyAction
  busy: BusyAction | null
  icon: ReactNode
  label: string
  busyLabel?: string
  tone: keyof typeof BUTTON_TONES
  submit?: boolean
  disabled?: boolean
  onClick?: () => void
}) {
  const isBusy = busy === kind
  return (
    <button
      type={submit ? 'submit' : 'button'}
      onClick={onClick}
      disabled={disabled || busy !== null}
      className={`flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[13px] font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${BUTTON_TONES[tone]}`}
    >
      {isBusy ? <SpinnerIcon width={14} height={14} /> : icon}
      {isBusy && busyLabel ? busyLabel : label}
    </button>
  )
}

interface CheckPanelProps {
  projectId: number
  worktree?: string
  onWorktreeDeleted?: (projectId: number, worktree: string) => void
}

export function CheckPanel({ projectId, worktree, onWorktreeDeleted }: CheckPanelProps) {
  const { t } = useTranslation()
  const confirm = useConfirm()
  const { data, error, loading, reload } = useAsyncData(
    () => fetchCurrentPullRequest(projectId, worktree),
    t('ide.pullRequestError'),
    [projectId, worktree],
  )
  const [busy, setBusy] = useState<BusyAction | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [newBranch, setNewBranch] = useState('')

  const status = data
  const pullRequest = status?.pull_request ?? null
  const isDefaultBranch = status?.is_default_branch ?? false
  const canDeleteWorktree = Boolean(worktree) && status?.is_primary_worktree === false

  async function run(kind: BusyAction, action: () => Promise<void>, fallback: string) {
    if (busy) return
    setBusy(kind)
    setActionError(null)
    try {
      await action()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : fallback)
    } finally {
      setBusy(null)
    }
  }

  function handleCreate() {
    const branch = status?.branch
    if (!branch) return
    void run(
      'create',
      async () => {
        await createPullRequest(projectId, branch, worktree)
        reload()
      },
      t('ide.prFailed'),
    )
  }

  function handleCreateBranch() {
    const branch = newBranch.trim()
    if (!branch) return
    void run(
      'branch',
      async () => {
        await createBranch(projectId, branch, worktree)
        setNewBranch('')
        reload()
      },
      t('ide.createBranchFailed'),
    )
  }

  function handleMerge() {
    void run(
      'merge',
      async () => {
        await mergePullRequest(projectId, worktree)
        reload()
      },
      t('ide.prMergeFailed'),
    )
  }

  async function handleDeleteWorktree() {
    if (!worktree) return
    const approved = await confirm({
      message: t('ide.deleteWorktreeConfirm', { name: worktree }),
      destructive: true,
    })
    if (!approved) return
    void run(
      'delete',
      async () => {
        await deleteWorktree(projectId, worktree)
        onWorktreeDeleted?.(projectId, worktree)
        void refreshProjectWorktrees(projectId)
      },
      t('ide.deleteWorktreeFailed'),
    )
  }

  const state = pullRequest?.state.toUpperCase()

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
        <span className="truncate">{t('ide.check')}</span>
        <button
          type="button"
          aria-label={t('ide.refresh')}
          title={t('ide.refresh')}
          onClick={reload}
          className="ml-auto rounded p-2 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] md:p-0.5"
        >
          <RefreshIcon width={14} height={14} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-3">
        {loading && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">{t('common.loading')}</p>
        )}
        {!loading && error && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--danger)]">{error}</p>
        )}

        {!loading && !error && status && (
          <>
            {isDefaultBranch ? (
              <div className="mx-1.5 mt-2 rounded-md border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <div className="flex items-start gap-2">
                  <BranchIcon width={15} height={15} className="mt-0.5 shrink-0 text-[var(--muted-2)]" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-[var(--fg)]">
                      {t('ide.prOnDefaultBranch')}
                    </p>
                    <p className="mt-1 text-[12px] text-[var(--muted-2)]">
                      {t('ide.prSwitchBranchHint')}
                    </p>
                  </div>
                </div>
                <form
                  onSubmit={(event) => {
                    event.preventDefault()
                    handleCreateBranch()
                  }}
                  className="mt-3 space-y-2"
                >
                  <input
                    type="text"
                    value={newBranch}
                    onChange={(event) => setNewBranch(event.target.value)}
                    placeholder={t('ide.newBranchPlaceholder')}
                    aria-label={t('ide.branchName')}
                    className="w-full rounded-md border border-[var(--hover-strong-alt)] bg-[var(--input)] px-2.5 py-2 text-base text-[var(--fg)] placeholder:text-[var(--muted-3)] focus:border-[var(--accent)] focus:outline-none md:text-[12.5px]"
                  />
                  <ActionButton
                    kind="branch"
                    busy={busy}
                    tone="primary"
                    submit
                    disabled={newBranch.trim().length === 0}
                    icon={<BranchIcon width={14} height={14} />}
                    label={t('ide.createBranch')}
                  />
                </form>
              </div>
            ) : !pullRequest ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  handleCreate()
                }}
                className="mx-1.5 mt-2 space-y-2 rounded-md border border-[var(--border)] bg-[var(--surface-2)] p-3"
              >
                <div className="flex items-start gap-2">
                  <PrIcon width={15} height={15} className="mt-0.5 shrink-0 text-[var(--muted-2)]" />
                  <p className="min-w-0 flex-1 truncate font-mono text-[12px] text-[var(--muted)]">
                    {status.branch}
                  </p>
                </div>
                <ActionButton
                  kind="create"
                  busy={busy}
                  tone="primary"
                  submit
                  disabled={!status.branch}
                  icon={<PrIcon width={14} height={14} />}
                  label={t('ide.prCreate')}
                  busyLabel={t('ide.creatingPr')}
                />
              </form>
            ) : (
              <>
                <PullRequestCard pullRequest={pullRequest} />
                {state === 'OPEN' && (
                  <div className="mx-1.5 mt-2">
                    <ActionButton
                      kind="merge"
                      busy={busy}
                      tone="merge"
                      onClick={handleMerge}
                      icon={<PrIcon width={14} height={14} />}
                      label={t('ide.prMerge')}
                      busyLabel={t('ide.prMerging')}
                    />
                  </div>
                )}
                {state === 'MERGED' && canDeleteWorktree && (
                  <div className="mx-1.5 mt-2">
                    <ActionButton
                      kind="delete"
                      busy={busy}
                      tone="danger"
                      onClick={() => void handleDeleteWorktree()}
                      icon={<TrashIcon width={14} height={14} />}
                      label={t('ide.deleteWorktree')}
                    />
                  </div>
                )}
              </>
            )}

            {actionError && (
              <p role="alert" className="px-2.5 pt-2 text-[12px] text-[var(--danger)]">
                {actionError}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
