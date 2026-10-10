export type ChatStreamEvent =
  | {
      type: 'message_start'
      conversation: { id: string; title: string }
      user_message_id: number
      assistant_message_id: number
    }
  | { type: 'text_delta'; text: string }
  | {
      type: 'command_approval'
      approval_id: string
      command: string
      reason: string
    }
  | { type: 'command_approval_expired'; approval_id: string }
  | {
      type: 'proposal'
      id: string
      path: string
      diff: string
      status: 'pending' | 'applied' | 'rejected' | 'stale'
    }
  | { type: 'complete'; conversation_id: string; assistant_message_id: number; status: string }
  | { type: 'error'; code: string; message: string; assistant_message_id: number }

export async function consumeChatStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      pending += decoder.decode(value, { stream: !done })
      let newline = pending.indexOf('\n')
      while (newline !== -1) {
        const line = pending.slice(0, newline).trim()
        pending = pending.slice(newline + 1)
        if (line) onEvent(parseEvent(line))
        newline = pending.indexOf('\n')
      }
      if (done) break
    }
    if (pending.trim()) onEvent(parseEvent(pending.trim()))
  } finally {
    reader.releaseLock()
  }
}

function parseEvent(line: string): ChatStreamEvent {
  const value: unknown = JSON.parse(line)
  if (!value || typeof value !== 'object' || !('type' in value)) {
    throw new Error('Invalid chat stream event')
  }
  const event = value as Record<string, unknown>
  if (
    event.type === 'message_start' &&
    event.conversation &&
    typeof event.conversation === 'object' &&
    'id' in event.conversation &&
    typeof event.conversation.id === 'string' &&
    typeof event.user_message_id === 'number' &&
    typeof event.assistant_message_id === 'number'
  ) {
    return event as ChatStreamEvent
  }
  if (
    event.type === 'command_approval_expired' &&
    typeof event.approval_id === 'string'
  ) {
    return event as ChatStreamEvent
  }
  if (event.type === 'text_delta' && typeof event.text === 'string') {
    return event as ChatStreamEvent
  }
  if (
    event.type === 'command_approval' &&
    typeof event.approval_id === 'string' &&
    typeof event.command === 'string' &&
    typeof event.reason === 'string'
  ) {
    return event as ChatStreamEvent
  }
  if (
    event.type === 'proposal' &&
    typeof event.id === 'string' &&
    typeof event.path === 'string' &&
    typeof event.diff === 'string' &&
    (event.status === 'pending' ||
      event.status === 'applied' ||
      event.status === 'rejected' ||
      event.status === 'stale')
  ) {
    return event as ChatStreamEvent
  }
  if (
    event.type === 'complete' &&
    typeof event.conversation_id === 'string' &&
    typeof event.assistant_message_id === 'number' &&
    typeof event.status === 'string'
  ) {
    return event as ChatStreamEvent
  }
  if (
    event.type === 'error' &&
    typeof event.code === 'string' &&
    typeof event.message === 'string' &&
    typeof event.assistant_message_id === 'number'
  ) {
    return event as ChatStreamEvent
  }
  throw new Error('Invalid chat stream event')
}
