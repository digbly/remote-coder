import { ChatPanel } from './ChatPanel'

export function ChatTab({
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
  return (
    <ChatPanel
      projectId={projectId}
      tabId={tabId}
      active={active}
      conversationId={conversationId}
      onConversationChange={onConversationChange}
    />
  )
}
