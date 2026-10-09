export interface AgentDefinition {
  id: string
  label: string
  command: string
}

// Candidate coding agents the UI can offer. The server reports which of these
// are actually installed on the host so users do not have to declare them.
export const AGENT_CANDIDATES: readonly AgentDefinition[] = [
  { id: 'claude', label: 'Claude Code', command: 'claude' },
  { id: 'agy', label: 'Antigravity', command: 'agy' },
  { id: 'opencode', label: 'OpenCode', command: 'opencode' },
  { id: 'codex', label: 'Codex', command: 'codex' },
  { id: 'gemini', label: 'Gemini CLI', command: 'gemini' },
  { id: 'aider', label: 'Aider', command: 'aider' },
  { id: 'goose', label: 'Goose', command: 'goose' },
  { id: 'cursor-agent', label: 'Cursor Agent', command: 'cursor-agent' },
  { id: 'crush', label: 'Crush', command: 'crush' },
] as const
