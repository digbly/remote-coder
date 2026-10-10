import { ChatPanel } from './ChatPanel'

export function ChatTab({
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
  return (
    <ChatPanel
      projectId={projectId}
      tabId={tabId}
      active={active}
      conversationId={conversationId}
      onConversationChange={onConversationChange}
      onStreamingChange={onStreamingChange}
    />
  )
}
