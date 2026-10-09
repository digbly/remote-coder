export interface AgentDefinition {
  id: string
  label: string
  command: string
  args: string
  commit_args: string
  description: string
  homepage: string | null
  installed: boolean
  path: string | null
}
