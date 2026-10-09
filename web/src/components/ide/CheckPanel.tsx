import { useTranslation } from 'react-i18next'
import { fetchCurrentPullRequest, type GitPullRequestSummary } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { PrIcon, RefreshIcon } from './icons'

const STATE_COLORS: Record<string, string> = {
  OPEN: 'text-[#6fbf8b]',
  MERGED: 'text-[#8ab4f8]',
  CLOSED: 'text-[#d98b94]',
}

function stateColor(state: string): string {
  return STATE_COLORS[state.toUpperCase()] ?? 'text-[#8b9099]'
}

function PullRequestCard({ pullRequest }: { pullRequest: GitPullRequestSummary }) {
  const { t } = useTranslation()
  return (
    <div className="mx-1.5 mt-2 rounded-md border border-[#2c2e33] bg-[#202124] p-3">
      <div className="flex items-start gap-2">
        <PrIcon width={15} height={15} className="mt-0.5 shrink-0 text-[#7d828b]" />
        <div className="min-w-0 flex-1">
          <a
            href={pullRequest.url}
            target="_blank"
            rel="noreferrer"
            className="block truncate text-[13px] font-medium text-[#e6e8ec] hover:underline"
            title={pullRequest.title}
          >
            {pullRequest.title}
          </a>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
            <span className="text-[#7d828b]">#{pullRequest.number}</span>
            <span className={`font-medium ${stateColor(pullRequest.state)}`}>
              {pullRequest.state.toLowerCase()}
            </span>
            {pullRequest.is_draft && (
              <span className="rounded border border-[#3a3d42] px-1.5 py-px text-[10px] text-[#8b9099]">
                {t('ide.draft')}
              </span>
            )}
          </div>
          {pullRequest.head && pullRequest.base && (
            <p className="mt-1.5 truncate font-mono text-[11px] text-[#8b9099]">
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
      <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#8b9099]">
        <span className="truncate">{t('ide.check')}</span>
        <button
          type="button"
          aria-label={t('ide.refresh')}
          title={t('ide.refresh')}
          onClick={reload}
          className="ml-auto rounded p-0.5 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
        >
          <RefreshIcon width={14} height={14} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-3">
        {loading && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#7d828b]">{t('common.loading')}</p>
        )}
        {!loading && error && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#f0a9b0]">{error}</p>
        )}
        {!loading && !error && !pullRequest && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#7d828b]">{t('ide.noPullRequest')}</p>
        )}
        {!loading && !error && pullRequest && <PullRequestCard pullRequest={pullRequest} />}
      </div>
    </div>
  )
}
