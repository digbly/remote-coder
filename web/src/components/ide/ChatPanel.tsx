import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ArrowUpIcon,
  ChevronDownIcon,
  MonitorIcon,
  PlusIcon,
  WarningIcon,
} from './icons'
import { MarkdownMessage } from './MarkdownMessage'
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

const BRAND_GRADIENT = 'linear-gradient(90deg, #C75A45 0%, #D98A5B 100%)'
const USER_BUBBLE_GRADIENT = 'linear-gradient(90deg, #C75A45 0%, #D88962 100%)'
const brandStyle = { backgroundImage: BRAND_GRADIENT }

const MAX_TEXTAREA_HEIGHT = 192
const MIN_TEXTAREA_HEIGHT = 24

const pageBg = 'bg-[#F9F9F9] dark:bg-[#0F0F0F]'
const cardBg = 'bg-white dark:bg-[#1F1F1F]'
const subtleBg = 'bg-[#F2F2F2] dark:bg-[#272727]'
const cardBorder = 'border-[#E5E7EB] dark:border-[#2E2E2E]'
const primaryText = 'text-[#0F0F0F] dark:text-[#F1F1F1]'
const mutedText = 'text-[#6B6B6B] dark:text-[#AAAAAA]'
const dangerText = 'text-[#DC2626] dark:text-[#F87171]'
const accentText = 'text-[#C25C49]'
const accentBg = 'bg-[#C25C49]'
const dotIdle = 'bg-[#B8B8B8] dark:bg-[#555555]'
const focusRing =
  'focus:border-[#C25C49] focus:ring-2 focus:ring-[#C25C49]/30'
const placeholderText = 'placeholder:text-[#6B6B6B] dark:placeholder:text-[#AAAAAA]'

const compactSelectClass = `appearance-none rounded-full border border-[#E7E7E7] bg-[#F5F5F5] px-2.5 py-1 text-[11px] ${primaryText} outline-none transition ${focusRing} disabled:opacity-50`

const composerShell = `flex flex-col rounded-3xl border ${cardBorder} ${cardBg} px-3 pb-2 pt-3 shadow-sm transition focus-within:border-[#C25C49] focus-within:ring-2 focus-within:ring-[#C25C49]/25`
const composerIconButton = `inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${mutedText} transition hover:bg-black/5 disabled:opacity-40 dark:hover:bg-white/10`
const composerSendButton =
  'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white shadow-sm transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100'
const composerSelect = `max-w-[10.5rem] cursor-pointer appearance-none truncate rounded-full bg-transparent py-1 pl-2.5 pr-6 text-[12px] ${primaryText} outline-none transition hover:bg-black/5 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10`
const composerMetaItem = `inline-flex items-center gap-1.5 rounded-full bg-transparent px-1.5 py-1 text-[11px] ${mutedText} transition hover:bg-black/5 dark:hover:bg-white/10`

const gradientButton =
  'inline-flex items-center justify-center rounded-full font-medium text-white shadow-sm transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100'
const ghostButton = `inline-flex items-center justify-center rounded-full border ${cardBorder} ${subtleBg} px-3 py-1.5 text-xs ${primaryText} transition hover:brightness-95 disabled:opacity-50`

type ToolLabelKey =
  | 'chat.toolList'
  | 'chat.toolRead'
  | 'chat.toolSearch'
  | 'chat.toolPropose'
  | 'chat.toolCreate'
  | 'chat.toolDelete'
  | 'chat.toolMkdir'
  | 'chat.toolRmdir'
  | 'chat.toolMove'
  | 'chat.toolCommand'

const TOOL_LABEL_KEYS: Record<string, ToolLabelKey> = {
  list_project_files: 'chat.toolList',
  read_project_file: 'chat.toolRead',
  search_project_files: 'chat.toolSearch',
  propose_file_change: 'chat.toolPropose',
  create_project_file: 'chat.toolCreate',
  delete_project_file: 'chat.toolDelete',
  create_project_directory: 'chat.toolMkdir',
  delete_project_directory: 'chat.toolRmdir',
  move_project_entry: 'chat.toolMove',
  run_project_command: 'chat.toolCommand',
}

function ThinkingBlock({ text, streaming }: { text: string; streaming: boolean }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(streaming)
  const wasStreaming = useRef(streaming)
  useEffect(() => {
    if (wasStreaming.current && !streaming) setOpen(false)
    wasStreaming.current = streaming
  }, [streaming])

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={`flex items-center gap-1 text-xs font-medium ${mutedText} transition hover:opacity-80`}
      >
        <svg
          viewBox="0 0 20 20"
          aria-hidden="true"
          className={`h-3 w-3 transition-transform ${open ? 'rotate-90' : ''}`}
        >
          <path d="M7 5l6 5-6 5z" fill="currentColor" />
        </svg>
        {streaming ? t('chat.thinking') : t('chat.thinkingComplete')}
      </button>
      {open && (
        <div className={`mt-2 whitespace-pre-wrap break-words border-l-2 ${cardBorder} pl-3 text-xs italic leading-5 ${mutedText}`}>
          {text || t('chat.thinking')}
        </div>
      )}
    </div>
  )
}

function ToolSteps({ steps, streaming }: { steps: string[]; streaming: boolean }) {
  return (
    <ul className="mb-2 space-y-1">
      {steps.map((step, index) => {
        const running = streaming && index === steps.length - 1
        return (
          <li
            key={index}
            className={`flex items-center gap-1.5 text-xs ${running ? primaryText : mutedText}`}
          >
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${running ? accentBg : dotIdle}`}
            />
            <span className="truncate">{step}</span>
          </li>
        )
      })}
    </ul>
  )
}

export function ChatPanel({
  projectId,
  tabId,
  active,
  conversationId,
  onConversationChange,
  onStreamingChange,
}: {
  projectId: number
  tabId: string
  active: boolean
  conversationId?: string
  onConversationChange: (id: string | undefined, title?: string) => void
  onStreamingChange?: (streaming: boolean) => void
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
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const optimisticIdRef = useRef(0)
  const onStreamingChangeRef = useRef(onStreamingChange)

  useEffect(() => {
    onStreamingChangeRef.current = onStreamingChange
  }, [onStreamingChange])

  useEffect(() => {
    onStreamingChangeRef.current?.(streaming)
  }, [streaming])

  useEffect(() => {
    return () => onStreamingChangeRef.current?.(false)
  }, [])

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

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(Math.max(el.scrollHeight, MIN_TEXTAREA_HEIGHT), MAX_TEXTAREA_HEIGHT)}px`
  }, [draft])

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
    const optimisticUserId = optimisticIdRef.current - 1
    const optimisticAssistantId = optimisticUserId - 1
    optimisticIdRef.current = optimisticAssistantId
    let assistantId: number | null = optimisticAssistantId
    let activeConversationId = selectedConversation
    let streamCompleted = false
    setMessages((current) => [
      ...current,
      {
        id: optimisticUserId,
        role: 'user',
        content,
        thinking: '',
        status: 'completed',
        created_at: new Date().toISOString(),
      },
      {
        id: optimisticAssistantId,
        role: 'assistant',
        content: '',
        thinking: '',
        status: 'streaming',
        created_at: new Date().toISOString(),
      },
    ])
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
          setMessages((current) =>
            current.map((message) => {
              if (message.id === optimisticUserId) {
                return { ...message, id: streamEvent.user_message_id }
              }
              if (message.id === optimisticAssistantId) {
                return { ...message, id: streamEvent.assistant_message_id }
              }
              return message
            }),
          )
        } else if (streamEvent.type === 'text_delta') {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, content: message.content + streamEvent.text }
                : message,
            ),
          )
        } else if (streamEvent.type === 'thinking_delta') {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, thinking: message.thinking + streamEvent.text }
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
            target_path: streamEvent.target_path,
            change_type: streamEvent.change_type as AIChangeProposal['change_type'],
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
        } else if (streamEvent.type === 'notice') {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? { ...message, notice: streamEvent.message } : message,
            ),
          )
        } else if (streamEvent.type === 'tool_call') {
          const label = describeTool(streamEvent.name, streamEvent.path)
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, steps: [...(message.steps ?? []), label] }
                : message,
            ),
          )
        } else if (streamEvent.type === 'error') {
          setMessages((current) =>
            current.map((message) =>
              message.id === streamEvent.assistant_message_id
                ? { ...message, status: 'failed', error: streamEvent.message }
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

  function describeTool(name: string, path?: string): string {
    const labelKey = TOOL_LABEL_KEYS[name]
    const base = labelKey ? t(labelKey) : name
    return path ? `${base} · ${path}` : base
  }

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
      className={`flex h-full min-h-0 flex-col ${pageBg} ${primaryText}`}
    >
      <div className="flex items-center justify-end gap-2 px-4 pb-1 pt-2 text-[11px] text-[#666666]">
        <select
          className={`${compactSelectClass} max-w-40`}
          value={selectedConversation}
          onChange={(event) => void selectConversation(event.target.value)}
          disabled={streaming}
          aria-label={t('chat.history')}
        >
          <option value="">{t('chat.newConversation')}</option>
          {conversations.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-5">
        {loading && <p className={`text-center text-sm ${mutedText}`}>{t('common.loading')}</p>}
        {!loading && providers.length === 0 && (
          <div className="mx-auto mt-12 max-w-lg text-center">
            <p className={`text-sm font-medium ${primaryText}`}>{t('chat.noProviders')}</p>
            <p className={`mt-1 text-xs ${mutedText}`}>{t('chat.configureProvider')}</p>
          </div>
        )}
        {!loading && providers.length > 0 && messages.length === 0 && (
          <div className={`mx-auto mt-12 max-w-lg text-center text-sm ${mutedText}`}>
            {t('chat.empty')}
          </div>
        )}
        {loadError && <p className={`text-center text-sm ${dangerText}`}>{loadError}</p>}
        {messages.map((message) => {
          const isUser = message.role === 'user'
          return (
            <article
              key={`${tabId}-${message.id}`}
              style={isUser ? { backgroundImage: USER_BUBBLE_GRADIENT } : undefined}
              className={
                isUser
                  ? 'mx-auto w-full max-w-[1000px] rounded-2xl px-4 py-3 text-white shadow-none'
                  : 'mx-auto w-full max-w-[1000px] rounded-none border-0 bg-transparent px-0 py-2'
              }
            >
              {!isUser && message.thinking && (
                <ThinkingBlock text={message.thinking} streaming={message.status === 'streaming'} />
              )}
              {!isUser && message.steps && message.steps.length > 0 && (
                <ToolSteps steps={message.steps} streaming={message.status === 'streaming'} />
              )}
              {isUser ? (
                <div className="whitespace-pre-wrap break-words text-[15px] leading-7 text-white">
                  {message.content}
                </div>
              ) : message.content ? (
                <MarkdownMessage content={message.content} />
              ) : message.status === 'streaming' &&
                !message.thinking &&
                !message.steps?.length ? (
                <div className={`text-[15px] leading-7 ${primaryText}`}>{t('chat.thinking')}</div>
              ) : null}
              {message.status === 'failed' && (
                <p className={`mt-2 text-xs ${isUser ? 'text-white' : dangerText}`}>
                  {message.error || t('chat.failedStatus')}
                </p>
              )}
              {!isUser && message.notice && (
                <p className={`mt-2 text-xs ${accentText}`}>{message.notice}</p>
              )}
              {message.status === 'interrupted' && (
                <p className={`mt-2 text-xs ${isUser ? 'text-white' : mutedText}`}>
                  {t('chat.interrupted')}
                </p>
              )}
            </article>
          )
        })}
        {pendingCommand && (
          <article className={`mx-auto max-w-3xl rounded-2xl border border-[#F97316]/50 ${cardBg} px-4 py-3`}>
            <h3 className={`text-sm font-semibold ${primaryText}`}>
              {t('chat.commandApprovalTitle')}
            </h3>
            <p className={`mt-1 text-xs ${mutedText}`}>
              {t('chat.commandApprovalHint')}
            </p>
            <pre className={`mt-3 max-h-48 overflow-auto rounded-xl ${subtleBg} p-3 text-xs leading-5 ${primaryText}`}>
              <code>{pendingCommand.command}</code>
            </pre>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={() => void decideCommand(true)}
                disabled={approvalBusy}
                style={brandStyle}
                className={`${gradientButton} px-3 py-1.5 text-xs`}
              >
                {t('chat.runCommand')}
              </button>
              <button
                type="button"
                onClick={() => void decideCommand(false)}
                disabled={approvalBusy}
                className={ghostButton}
              >
                {t('chat.cancelCommand')}
              </button>
            </div>
          </article>
        )}
        {proposals.map((proposal) => (
          <article
            key={`proposal-${proposal.id}`}
            className={`mx-auto max-w-3xl rounded-2xl border border-[#F97316]/40 ${cardBg} px-4 py-3`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className={`text-sm font-semibold ${primaryText}`}>
                  {t('chat.proposalTitle')} · {t(`chat.proposalKind.${proposal.change_type}`)}
                </h3>
                <p className={`text-xs ${mutedText}`}>
                  {proposal.path}
                  {proposal.change_type === 'move' && proposal.target_path
                    ? ` → ${proposal.target_path}`
                    : ''}
                </p>
              </div>
              <span className={`text-xs ${mutedText}`}>
                {t(`chat.proposalStatus.${proposal.status}`)}
              </span>
            </div>
            {proposal.diff && (
              <pre className={`mt-3 max-h-80 overflow-auto rounded-xl ${subtleBg} p-3 text-xs leading-5 ${primaryText}`}>
                <code>{proposal.diff}</code>
              </pre>
            )}
            {proposal.status === 'pending' && (
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => void actOnProposal(proposal, 'apply')}
                  style={brandStyle}
                  className={`${gradientButton} px-3 py-1.5 text-xs`}
                >
                  {t('chat.applyChange')}
                </button>
                <button
                  type="button"
                  onClick={() => void actOnProposal(proposal, 'reject')}
                  className={ghostButton}
                >
                  {t('chat.rejectChange')}
                </button>
              </div>
            )}
          </article>
        ))}
        <div ref={endRef} />
      </div>

      <div className={`border-t ${cardBorder} ${cardBg} px-4 pb-3 pt-4`}>
        {error && <p className={`mx-auto mb-2 max-w-3xl text-sm ${dangerText}`}>{error}</p>}
        {!provider && providers.length > 0 && (
          <p className={`mx-auto mb-2 max-w-3xl text-xs ${mutedText}`}>
            {t('chat.selectProvider')}
          </p>
        )}
        {provider && models.length === 0 && (
          <p className={`mx-auto mb-2 max-w-3xl text-xs ${mutedText}`}>
            {t('chat.modelsUnavailable')}
          </p>
        )}
        <form onSubmit={(event) => void send(event)} className="mx-auto max-w-3xl">
          <div className={composerShell}>
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  event.currentTarget.form?.requestSubmit()
                }
              }}
              rows={1}
              maxLength={16000}
              placeholder={t('chat.messagePlaceholder')}
              style={{ maxHeight: MAX_TEXTAREA_HEIGHT }}
              className={`min-h-9 w-full resize-none overflow-y-auto bg-transparent px-1 py-1 text-sm leading-6 ${primaryText} outline-none ${placeholderText} disabled:opacity-50`}
              disabled={loading || streaming}
            />
            <div className="mt-1 flex items-center gap-1">
              <button
                type="button"
                onClick={() => void selectConversation('')}
                className={composerIconButton}
                title={t('chat.newConversation')}
                aria-label={t('chat.newConversation')}
                disabled={loading || streaming}
              >
                <PlusIcon className="h-4 w-4" />
              </button>

              <label className="relative inline-flex items-center">
                <select
                  className={composerSelect}
                  value={providerId ?? ''}
                  onChange={(event) => {
                    const next = Number(event.target.value) || null
                    setProviderId(next)
                    setModels([])
                    setModelId('')
                  }}
                  disabled={loading || streaming || permissionSaving}
                  aria-label={t('chat.provider')}
                  title={t('chat.provider')}
                >
                  <option value="">{t('chat.selectProvider')}</option>
                  {providers.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
                <ChevronDownIcon className="pointer-events-none absolute right-1.5 top-1/2 h-3 w-3 -translate-y-1/2 opacity-50" />
              </label>

              <label className="relative inline-flex items-center">
                <select
                  className={composerSelect}
                  value={modelId}
                  onChange={(event) => setModelId(event.target.value)}
                  disabled={!models.length || streaming}
                  aria-label={t('chat.model')}
                  title={t('chat.model')}
                >
                  <option value="">{t('chat.selectModel')}</option>
                  {(providerId ? models : []).map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.display_name}
                    </option>
                  ))}
                </select>
                <ChevronDownIcon className="pointer-events-none absolute right-1.5 top-1/2 h-3 w-3 -translate-y-1/2 opacity-50" />
              </label>

              <div className="flex-1" />

              {streaming ? (
                <button
                  type="button"
                  onClick={() => abortRef.current?.abort()}
                  className={`inline-flex h-8 shrink-0 items-center justify-center rounded-full border ${cardBorder} ${subtleBg} px-3 text-xs ${primaryText} transition hover:brightness-95`}
                >
                  {t('chat.stop')}
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!canSend}
                  aria-label={t('chat.send')}
                  title={t('chat.send')}
                  style={brandStyle}
                  className={composerSendButton}
                >
                  <ArrowUpIcon className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>

          <div className={`mt-2 flex flex-wrap items-center gap-3 px-1.5 text-[11px] ${mutedText}`}>
            <span className="inline-flex items-center gap-1.5">
              <MonitorIcon className="h-3.5 w-3.5" />
              {t('chat.environmentLocal')}
            </span>
            <label
              className={`relative inline-flex cursor-pointer items-center gap-1.5 ${composerMetaItem}`}
            >
              <WarningIcon className="h-3.5 w-3.5" />
              <select
                className="cursor-pointer appearance-none bg-transparent pr-4 text-[11px] outline-none disabled:cursor-not-allowed disabled:opacity-50"
                value={commandPermission}
                onChange={(event) => {
                  const mode = event.target.value
                  if (mode === 'manual' || mode === 'risky' || mode === 'allow_all') {
                    void changeCommandPermission(mode)
                  }
                }}
                disabled={loading || streaming || permissionSaving}
                aria-label={t('chat.commandPermission')}
                title={t('chat.commandPermission')}
              >
                <option value="manual">{t('chat.permissionManual')}</option>
                <option value="risky">{t('chat.permissionRisky')}</option>
                <option value="allow_all">{t('chat.permissionAllowAll')}</option>
              </select>
              <ChevronDownIcon className="pointer-events-none absolute right-0.5 top-1/2 h-3 w-3 -translate-y-1/2 opacity-50" />
            </label>
          </div>

          <p className={`mt-1.5 px-1.5 text-[11px] ${mutedText}`}>
            {t('chat.readOnlyNotice')}
          </p>
        </form>
      </div>
    </section>
  )
}
