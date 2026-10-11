import { useTranslation } from 'react-i18next'
import { fetchAgentSessions, type AgentSession } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { ChatIcon, HistoryIcon, RefreshIcon, TerminalIcon } from './icons'

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString()
}

function SessionRow({
  session,
  onResume,
}: {
  session: AgentSession
  onResume: () => void
}) {
  const { t } = useTranslation()
  const isChat = session.source === 'chat'
  const timestamp = formatTimestamp(session.updated_at)
  return (
    <div className="group flex items-start gap-2 rounded-md px-2 py-1.5 transition hover:bg-[var(--hover-subtle)]">
      <span className="mt-0.5 shrink-0 text-[var(--muted-2)]">
        {isChat ? <ChatIcon width={14} height={14} /> : <TerminalIcon width={14} height={14} />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] text-[var(--fg-2)]" title={session.title}>
          {session.title || t('sessions.untitled')}
        </p>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--muted-2)]">
          {!isChat && session.agent_label && (
            <span className="rounded bg-[var(--chip)] px-1.5 py-px text-[10px]">
              {session.agent_label}
            </span>
          )}
          {timestamp && <span className="truncate">{timestamp}</span>}
        </div>
      </div>
      <button
        type="button"
        onClick={onResume}
        title={t('sessions.resume')}
        className="shrink-0 rounded-md border border-[var(--border-strong-alt)] px-2 py-1 text-[11px] text-[var(--fg-2)] opacity-100 transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
      >
        {t('sessions.resume')}
      </button>
    </div>
  )
}

interface AgentSessionPanelProps {
  projectId: number
  worktree?: string
  onResumeChat: (conversationId: string, title: string) => void
  onResumeSession: (session: AgentSession) => void
}

export function AgentSessionPanel({
  projectId,
  worktree,
  onResumeChat,
  onResumeSession,
}: AgentSessionPanelProps) {
  const { t } = useTranslation()
  const { data, error, loading, reload } = useAsyncData(
    () => fetchAgentSessions(projectId, worktree),
    t('sessions.loadFailed'),
    [projectId, worktree],
  )

  const sessions = data ?? []
  const chatSessions = sessions.filter((session) => session.source === 'chat')
  const cliSessions = sessions.filter((session) => session.source === 'cli')

  function resume(session: AgentSession) {
    if (session.source === 'chat') {
      onResumeChat(session.id, session.title)
    } else {
      onResumeSession(session)
    }
  }

  function renderSection(title: string, items: AgentSession[]) {
    if (items.length === 0) return null
    return (
      <div className="mb-2">
        <p className="px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-2)]">
          {title}
        </p>
        <div className="space-y-0.5">
          {items.map((session) => (
            <SessionRow
              key={`${session.source}:${session.id}`}
              session={session}
              onResume={() => resume(session)}
            />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
        <HistoryIcon width={14} height={14} />
        <span className="truncate">{t('sessions.title')}</span>
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
        {!loading && !error && sessions.length === 0 && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">{t('sessions.empty')}</p>
        )}
        {!loading && !error && sessions.length > 0 && (
          <div className="pt-1">
            {renderSection(t('sessions.cliSection'), cliSessions)}
            {renderSection(t('sessions.chatSection'), chatSessions)}
          </div>
        )}
      </div>
    </div>
  )
}
