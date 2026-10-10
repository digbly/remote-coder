import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  decideAICommand,
  consumeChatStream,
  fetchAICommandPermission,
  fetchAIConversation,
  fetchAIConversations,
  fetchAIProviderModels,
  fetchAIProposals,
  fetchAIProviders,
  openAIChatStream,
  updateAIProposal,
  updateAICommandPermission,
  type AIChatMessage,
  type AICommandPermission,
  type AIChangeProposal,
  type AIConversation,
  type AIProvider,
  type AIProviderModel,
} from '../../lib/chat'

const selectClass =
  'rounded-md border border-[var(--border)] bg-[var(--bg)] px-2.5 py-1.5 text-xs text-[var(--fg)] outline-none focus:border-indigo-500'

export function ChatPanel({
  projectId,
  tabId,
  active,
  conversationId,
  onConversationChange,
}: {
  projectId: number
  tabId: string
  active: boolean
  conversationId?: string
  onConversationChange: (id: string | undefined, title?: string) => void
}) {
  const { t } = useTranslation()
  const [providers, setProviders] = useState<AIProvider[]>([])
  const [providerId, setProviderId] = useState<number | null>(null)
  const [models, setModels] = useState<AIProviderModel[]>([])
  const [modelId, setModelId] = useState('')
  const [conversations, setConversations] = useState<AIConversation[]>([])
  const [proposals, setProposals] = useState<AIChangeProposal[]>([])
  const [commandPermission, setCommandPermission] = useState<AICommandPermission>('manual')
  const [permissionSaving, setPermissionSaving] = useState(false)
  const [pendingCommand, setPendingCommand] = useState<{
    approvalId: string
    command: string
  } | null>(null)
  const [approvalBusy, setApprovalBusy] = useState(false)
  const [selectedConversation, setSelectedConversation] = useState(conversationId ?? '')
  const [messages, setMessages] = useState<AIChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      fetchAIProviders(),
      fetchAIConversations(projectId),
      fetchAICommandPermission(projectId),
    ])
      .then(([providerList, conversationList, permission]) => {
        if (!alive) return
        setProviders(providerList.providers)
        setProviderId((current) => current ?? providerList.providers[0]?.id ?? null)
        setConversations(conversationList)
        setCommandPermission(permission)
        setLoadError('')
      })
      .catch((reason: unknown) => {
        if (alive) setLoadError(reason instanceof Error ? reason.message : t('chat.loadFailed'))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
      abortRef.current?.abort()
    }
  }, [projectId, t])

  useEffect(() => {
    if (!providerId) {
      return
    }
    let alive = true
    fetchAIProviderModels(providerId)
      .then((result) => {
        if (!alive) return
        setModels(result)
        setModelId((current) =>
          result.some((model) => model.id === current)
            ? current
            : (result[0]?.id ?? ''),
        )
      })
      .catch((reason: unknown) => {
        if (alive) setError(reason instanceof Error ? reason.message : t('chat.modelsFailed'))
      })
    return () => {
      alive = false
    }
  }, [providerId, t])

  useEffect(() => {
    if (!conversationId || streaming) return
    let alive = true
    Promise.all([
      fetchAIConversation(projectId, conversationId),
      fetchAIProposals(projectId, conversationId),
    ])
      .then(([detail, savedProposals]) => {
        if (!alive) return
        setMessages(detail.messages)
        setProviderId(detail.conversation.provider_id)
        setModelId(detail.conversation.model_id)
        setProposals(savedProposals)
        setError('')
      })
      .catch((reason: unknown) => {
        if (alive) setLoadError(reason instanceof Error ? reason.message : t('chat.loadFailed'))
      })
    return () => {
      alive = false
    }
  }, [conversationId, projectId, streaming, t])

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [messages, pendingCommand])

  async function refreshConversations(): Promise<AIConversation[]> {
    const result = await fetchAIConversations(projectId)
    setConversations(result)
    return result
  }

  async function changeCommandPermission(mode: AICommandPermission) {
    setPermissionSaving(true)
    setError('')
    try {
      setCommandPermission(await updateAICommandPermission(projectId, mode))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('chat.permissionSaveFailed'))
    } finally {
      setPermissionSaving(false)
    }
  }

  async function decideCommand(approved: boolean) {
    if (!pendingCommand || approvalBusy) return
    setApprovalBusy(true)
    setError('')
    try {
      await decideAICommand(projectId, pendingCommand.approvalId, approved)
      setPendingCommand(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('chat.commandDecisionFailed'))
      abortRef.current?.abort()
    } finally {
      setApprovalBusy(false)
    }
  }

  async function selectConversation(id: string) {
    setSelectedConversation(id)
    setError('')
    if (!id) {
      setMessages([])
      setProposals([])
      onConversationChange(undefined)
      return
    }
    try {
      const [detail, savedProposals] = await Promise.all([
        fetchAIConversation(projectId, id),
        fetchAIProposals(projectId, id),
      ])
      setMessages(detail.messages)
      setProviderId(detail.conversation.provider_id)
      setModelId(detail.conversation.model_id)
      setProposals(savedProposals)
      onConversationChange(id, detail.conversation.title)
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : t('chat.loadFailed'))
    }
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = draft.trim()
    if (!content || !providerId || !modelId || streaming) return
    setDraft('')
    setError('')
    setLoadError('')
    setStreaming(true)
    const controller = new AbortController()
    abortRef.current = controller
    let assistantId: number | null = null
    let activeConversationId = selectedConversation
    let streamCompleted = false
    try {
      const response = await openAIChatStream(
        projectId,
        {
          conversation_id: selectedConversation || null,
          provider_id: providerId,
          model_id: modelId,
          message: content,
        },
        controller.signal,
      )
      if (!response.body) throw new Error(t('chat.streamUnavailable'))
      await consumeChatStream(response.body, (streamEvent) => {
        if (streamEvent.type === 'message_start') {
          assistantId = streamEvent.assistant_message_id
          activeConversationId = streamEvent.conversation.id
          setSelectedConversation(streamEvent.conversation.id)
          onConversationChange(streamEvent.conversation.id, streamEvent.conversation.title)
          setMessages((current) => [
            ...current,
            {
              id: streamEvent.user_message_id,
              role: 'user',
              content,
              status: 'completed',
              created_at: new Date().toISOString(),
            },
            {
              id: streamEvent.assistant_message_id,
              role: 'assistant',
              content: '',
              status: 'streaming',
              created_at: new Date().toISOString(),
            },
          ])
        } else if (streamEvent.type === 'text_delta') {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, content: message.content + streamEvent.text }
                : message,
            ),
          )
        } else if (streamEvent.type === 'command_approval') {
          setPendingCommand({
            approvalId: streamEvent.approval_id,
            command: streamEvent.command,
          })
        } else if (streamEvent.type === 'command_approval_expired') {
          setPendingCommand(null)
          setError(t('chat.commandApprovalExpired'))
        } else if (streamEvent.type === 'proposal') {
          const proposal: AIChangeProposal = {
            id: streamEvent.id,
            conversation_id: activeConversationId,
            path: streamEvent.path,
            diff: streamEvent.diff,
            status: streamEvent.status,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }
          setProposals((current) => [
            ...current.filter((item) => item.id !== proposal.id),
            proposal,
          ])
        } else if (streamEvent.type === 'complete') {
          streamCompleted = true
          setMessages((current) =>
            current.map((message) =>
              message.id === streamEvent.assistant_message_id
                ? { ...message, status: 'completed' }
                : message,
            ),
          )
        } else if (streamEvent.type === 'error') {
          setError(streamEvent.message)
          setMessages((current) =>
            current.map((message) =>
              message.id === streamEvent.assistant_message_id
                ? { ...message, status: 'failed' }
                : message,
            ),
          )
        }
      })
      try {
        const list = await refreshConversations()
        const activeConversation = list.find((item) => item.id === activeConversationId) ?? list[0]
        if (activeConversation) onConversationChange(activeConversation.id, activeConversation.title)
        if (activeConversation) {
          setProposals(await fetchAIProposals(projectId, activeConversation.id))
        }
      } catch (reason) {
        setLoadError(reason instanceof Error ? reason.message : t('chat.loadFailed'))
      }
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : t('chat.sendFailed'))
        if (assistantId !== null && !streamCompleted) {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? { ...message, status: 'interrupted' } : message,
            ),
          )
        }
      } else if (assistantId !== null && !streamCompleted) {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId ? { ...message, status: 'interrupted' } : message,
          ),
        )
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setPendingCommand(null)
      setStreaming(false)
    }
  }

  const provider = providers.find((item) => item.id === providerId)
  const canSend = Boolean(provider && modelId && draft.trim() && !streaming)

  async function actOnProposal(proposal: AIChangeProposal, action: 'apply' | 'reject') {
    if (!selectedConversation) return
    setError('')
    try {
      const updated = await updateAIProposal(
        projectId,
        selectedConversation,
        proposal.id,
        action,
      )
      setProposals((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('chat.proposalActionFailed'))
      if (action === 'apply') {
        try {
          setProposals(await fetchAIProposals(projectId, selectedConversation))
        } catch {
          setLoadError(t('chat.loadFailed'))
        }
      }
    }
  }

  return (
    <section
      aria-hidden={!active}
      data-active={active}
      className="flex h-full min-h-0 flex-col bg-[var(--bg)]"
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-2.5">
        <label className="text-xs text-[var(--muted-2)]">
          {t('chat.provider')}
          <select
            className={`ml-2 ${selectClass}`}
            value={providerId ?? ''}
            onChange={(event) => {
              const next = Number(event.target.value) || null
              setProviderId(next)
              setModels([])
              setModelId('')
            }}
            disabled={loading || streaming || permissionSaving}
          >
            <option value="">{t('chat.selectProvider')}</option>
            {providers.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} ({item.kind})
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-[var(--muted-2)]">
          {t('chat.commandPermission')}
          <select
            className={`ml-2 ${selectClass}`}
            value={commandPermission}
            onChange={(event) => {
              const mode = event.target.value
              if (mode === 'manual' || mode === 'risky' || mode === 'allow_all') {
                void changeCommandPermission(mode)
              }
            }}
            disabled={loading || streaming || permissionSaving}
            aria-label={t('chat.commandPermission')}
          >
            <option value="manual">{t('chat.permissionManual')}</option>
            <option value="risky">{t('chat.permissionRisky')}</option>
            <option value="allow_all">{t('chat.permissionAllowAll')}</option>
          </select>
        </label>
        <label className="text-xs text-[var(--muted-2)]">
          {t('chat.model')}
          <select
            className={`ml-2 ${selectClass}`}
            value={modelId}
            onChange={(event) => setModelId(event.target.value)}
            disabled={!models.length || streaming}
          >
            <option value="">{t('chat.selectModel')}</option>
            {(providerId ? models : []).map((model) => (
              <option key={model.id} value={model.id}>
                {model.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="ml-auto text-xs text-[var(--muted-2)]">
          {t('chat.history')}
          <select
            className={`ml-2 max-w-56 ${selectClass}`}
            value={selectedConversation}
            onChange={(event) => void selectConversation(event.target.value)}
            disabled={streaming}
          >
            <option value="">{t('chat.newConversation')}</option>
            {conversations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5">
        {loading && <p className="text-center text-sm text-[var(--muted-2)]">{t('common.loading')}</p>}
        {!loading && providers.length === 0 && (
          <div className="mx-auto mt-12 max-w-lg text-center">
            <p className="text-sm font-medium text-[var(--fg-2)]">{t('chat.noProviders')}</p>
            <p className="mt-1 text-xs text-[var(--muted-2)]">{t('chat.configureProvider')}</p>
          </div>
        )}
        {!loading && providers.length > 0 && messages.length === 0 && (
          <div className="mx-auto mt-12 max-w-lg text-center text-sm text-[var(--muted-2)]">
            {t('chat.empty')}
          </div>
        )}
        {loadError && <p className="text-center text-sm text-[var(--danger)]">{loadError}</p>}
        {messages.map((message) => (
          <article
            key={`${tabId}-${message.id}`}
            className={`mx-auto max-w-3xl rounded-xl border border-[var(--border)] p-4 ${
              message.role === 'user' ? 'bg-[var(--surface)]' : 'bg-[var(--surface-2)]'
            }`}
          >
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--muted-2)]">
              {message.role === 'user' ? t('chat.you') : t('chat.assistant')}
            </p>
            <div className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--fg-2)]">
              {message.content || (message.status === 'streaming' ? t('chat.thinking') : '')}
            </div>
            {message.status === 'failed' && (
              <p className="mt-2 text-xs text-[var(--danger)]">{t('chat.failedStatus')}</p>
            )}
            {message.status === 'interrupted' && (
              <p className="mt-2 text-xs text-[var(--muted-2)]">{t('chat.interrupted')}</p>
            )}
          </article>
        ))}
        {pendingCommand && (
          <article className="mx-auto max-w-3xl rounded-xl border border-amber-500/50 bg-[var(--surface)] p-4">
            <h3 className="text-sm font-semibold text-[var(--fg-strong)]">
              {t('chat.commandApprovalTitle')}
            </h3>
            <p className="mt-1 text-xs text-[var(--muted-2)]">
              {t('chat.commandApprovalHint')}
            </p>
            <pre className="mt-3 max-h-48 overflow-auto rounded-md bg-[var(--bg)] p-3 text-xs leading-5 text-[var(--fg-2)]">
              <code>{pendingCommand.command}</code>
            </pre>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={() => void decideCommand(true)}
                disabled={approvalBusy}
                className="rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
              >
                {t('chat.runCommand')}
              </button>
              <button
                type="button"
                onClick={() => void decideCommand(false)}
                disabled={approvalBusy}
                className="rounded-md border border-[var(--border-strong)] px-3 py-1.5 text-xs text-[var(--fg-2)] hover:bg-[var(--hover)] disabled:opacity-50"
              >
                {t('chat.cancelCommand')}
              </button>
            </div>
          </article>
        )}
        {proposals.map((proposal) => (
          <article
            key={`proposal-${proposal.id}`}
            className="mx-auto max-w-3xl rounded-xl border border-amber-500/40 bg-[var(--surface)] p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-[var(--fg-strong)]">
                  {t('chat.proposalTitle')}
                </h3>
                <p className="text-xs text-[var(--muted-2)]">{proposal.path}</p>
              </div>
              <span className="text-xs text-[var(--muted-2)]">
                {t(`chat.proposalStatus.${proposal.status}`)}
              </span>
            </div>
            <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-[var(--bg)] p-3 text-xs leading-5 text-[var(--fg-2)]">
              <code>{proposal.diff}</code>
            </pre>
            {proposal.status === 'pending' && (
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => void actOnProposal(proposal, 'apply')}
                  className="rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600"
                >
                  {t('chat.applyChange')}
                </button>
                <button
                  type="button"
                  onClick={() => void actOnProposal(proposal, 'reject')}
                  className="rounded-md border border-[var(--border-strong)] px-3 py-1.5 text-xs text-[var(--fg-2)] hover:bg-[var(--hover)]"
                >
                  {t('chat.rejectChange')}
                </button>
              </div>
            )}
          </article>
        ))}
        <div ref={endRef} />
      </div>

      <div className="border-t border-[var(--border)] bg-[var(--surface)] p-4">
        {error && <p className="mx-auto mb-2 max-w-3xl text-sm text-[var(--danger)]">{error}</p>}
        {!provider && providers.length > 0 && (
          <p className="mx-auto mb-2 max-w-3xl text-xs text-[var(--muted-2)]">
            {t('chat.selectProvider')}
          </p>
        )}
        {provider && models.length === 0 && (
          <p className="mx-auto mb-2 max-w-3xl text-xs text-[var(--muted-2)]">
            {t('chat.modelsUnavailable')}
          </p>
        )}
        <form onSubmit={(event) => void send(event)} className="mx-auto flex max-w-3xl gap-2">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                event.currentTarget.form?.requestSubmit()
              }
            }}
            rows={2}
            maxLength={16000}
            placeholder={t('chat.messagePlaceholder')}
            className="min-h-12 flex-1 resize-y rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--fg)] outline-none focus:border-indigo-500"
            disabled={loading || streaming}
          />
          {streaming ? (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="self-end rounded-md border border-[var(--border-strong)] px-4 py-2 text-sm text-[var(--fg-2)] transition hover:bg-[var(--hover)]"
            >
              {t('chat.stop')}
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canSend}
              className="self-end rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t('chat.send')}
            </button>
          )}
        </form>
        <p className="mx-auto mt-1 max-w-3xl text-[11px] text-[var(--muted-3)]">
          {t('chat.readOnlyNotice')}
        </p>
      </div>
    </section>
  )
}
