import { useTranslation } from 'react-i18next'
import { fetchCurrentPullRequest, type GitPullRequestSummary } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { PrIcon, RefreshIcon } from './icons'

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

interface CheckPanelProps {
  projectId: number
}

export function CheckPanel({ projectId }: CheckPanelProps) {
  const { t } = useTranslation()
  const { data, error, loading, reload } = useAsyncData(
    () => fetchCurrentPullRequest(projectId),
    t('ide.pullRequestError'),
    [projectId],
  )
  const pullRequest = data?.pull_request ?? null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
        <span className="truncate">{t('ide.check')}</span>
        <button
          type="button"
          aria-label={t('ide.refresh')}
          title={t('ide.refresh')}
          onClick={reload}
          className="ml-auto rounded p-0.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
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
        {!loading && !error && !pullRequest && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">{t('ide.noPullRequest')}</p>
        )}
        {!loading && !error && pullRequest && <PullRequestCard pullRequest={pullRequest} />}
      </div>
    </div>
  )
}
