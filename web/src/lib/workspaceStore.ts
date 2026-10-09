import { launchCommand, type AgentDefinition } from './agents'
import { normalizeLayout, type LayoutState } from './layoutStore'

export type TabKind = 'terminal' | 'editor'

export interface WorkspaceTab {
  id: string
  title: string
  kind: TabKind
  projectId?: number
  worktree?: string
  agentCommand?: string
}

export interface ProjectWorkspace {
  tabs: WorkspaceTab[]
  activeId: string | null
}

export interface ActiveProjectRef {
  id: number
  name: string
}

export interface SyncedState {
  workspaces: Record<number, ProjectWorkspace>
  layout: LayoutState
}

export interface NewTerminalOptions {
  worktree?: string
  agent?: AgentDefinition
}

export function newTerminalId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isTab(value: unknown): value is WorkspaceTab {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.title === 'string' &&
    (value.kind === 'terminal' || value.kind === 'editor') &&
    (value.projectId === undefined || typeof value.projectId === 'number') &&
    (value.worktree === undefined || typeof value.worktree === 'string') &&
    (value.agentCommand === undefined || typeof value.agentCommand === 'string')
  )
}

function parseWorkspace(value: unknown, projectId: number): ProjectWorkspace | null {
  if (!isRecord(value) || !Array.isArray(value.tabs)) return null
  const tabs = value.tabs.filter(isTab)
  if (tabs.length !== value.tabs.length) return null

  const scoped = tabs.map((tab) => ({ ...tab, projectId }))
  const activeId =
    typeof value.activeId === 'string' && scoped.some((tab) => tab.id === value.activeId)
      ? value.activeId
      : (scoped[scoped.length - 1]?.id ?? null)
  return { tabs: scoped, activeId }
}

function countByLabel(tabs: WorkspaceTab[], label: string): number {
  return tabs.filter((tab) => tab.title === label || tab.title.startsWith(`${label} (`)).length
}

export function withNewTerminal(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
  options: NewTerminalOptions = {},
): Record<number, ProjectWorkspace> {
  const { agent, worktree } = options
  const tabs = workspaces[project.id]?.tabs ?? []
  const id = newTerminalId()
  const label = agent ? agent.label : worktree || project.name
  const count = countByLabel(tabs, label)
  const tab: WorkspaceTab = {
    id,
    title: count === 0 ? label : `${label} (${count + 1})`,
    kind: 'terminal',
    projectId: project.id,
    ...(worktree ? { worktree } : {}),
    ...(agent ? { agentCommand: launchCommand(agent) } : {}),
  }
  return {
    ...workspaces,
    [project.id]: { tabs: [...tabs, tab], activeId: id },
  }
}

export function ensureWorkspace(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
): Record<number, ProjectWorkspace> {
  const existing = workspaces[project.id]
  if (existing && existing.tabs.length > 0) return workspaces
  return withNewTerminal(workspaces, project)
}

export function emptySyncedState(): SyncedState {
  return { workspaces: {}, layout: normalizeLayout(undefined) }
}

export function parseSyncedState(value: unknown): SyncedState | null {
  if (!isRecord(value) || !isRecord(value.workspaces)) return null

  const workspaces: Record<number, ProjectWorkspace> = {}
  for (const [key, raw] of Object.entries(value.workspaces)) {
    const projectId = Number(key)
    if (!Number.isInteger(projectId)) continue
    const workspace = parseWorkspace(raw, projectId)
    if (workspace === null) continue
    workspaces[projectId] = workspace
  }

  return {
    workspaces,
    layout: normalizeLayout(value.layout),
  }
}
