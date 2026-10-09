export interface AgentDefinition {
  id: string
  label: string
  command: string
  args: string
}

export interface AgentOverride {
  command: string
  args: string
}

// Candidate coding agents the UI can offer. The server reports which of these
// are actually installed on the host so users do not have to declare them.
export const AGENT_CANDIDATES: readonly AgentDefinition[] = [
  { id: 'claude', label: 'Claude Code', command: 'claude', args: '' },
  { id: 'agy', label: 'Antigravity', command: 'agy', args: '' },
  { id: 'opencode', label: 'OpenCode', command: 'opencode', args: '' },
  { id: 'codex', label: 'Codex', command: 'codex', args: '' },
  { id: 'gemini', label: 'Gemini CLI', command: 'gemini', args: '' },
  { id: 'aider', label: 'Aider', command: 'aider', args: '' },
  { id: 'goose', label: 'Goose', command: 'goose', args: '' },
  { id: 'cursor-agent', label: 'Cursor Agent', command: 'cursor-agent', args: '' },
  { id: 'crush', label: 'Crush', command: 'crush', args: '' },
]

export function resolveAgents(overrides: Record<string, AgentOverride>): AgentDefinition[] {
  return AGENT_CANDIDATES.map((agent) => ({
    id: agent.id,
    label: agent.label,
    command: overrides[agent.id]?.command.trim() || agent.command,
    args: overrides[agent.id]?.args ?? agent.args,
  }))
}

export function launchCommand(agent: AgentDefinition): string {
  const args = agent.args.trim()
  return args ? `${agent.command} ${args}` : agent.command
}
