import type { AgentDefinition } from './agents'
import { normalizeLayout, type LayoutState } from './layoutStore'

export type TabKind = 'terminal' | 'editor' | 'vscode' | 'chat'

export interface WorkspaceTab {
  id: string
  title: string
  kind: TabKind
  projectId?: number
  worktree?: string
  agentId?: string
  agentLabel?: string
  filePath?: string
  line?: number
  conversationId?: string
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

// Titles arrive from the PTY (OSC sequences) and are relayed to the sync
// server, so bound them to keep a runaway program from bloating tab state.
const MAX_TAB_TITLE_LENGTH = 120

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
    (value.kind === 'terminal' ||
      value.kind === 'editor' ||
      value.kind === 'vscode' ||
      value.kind === 'chat') &&
    (value.projectId === undefined || typeof value.projectId === 'number') &&
    (value.worktree === undefined || typeof value.worktree === 'string') &&
    (value.agentId === undefined || typeof value.agentId === 'string') &&
    (value.agentLabel === undefined || typeof value.agentLabel === 'string') &&
    (value.filePath === undefined || typeof value.filePath === 'string') &&
    (value.line === undefined || typeof value.line === 'number') &&
    (value.conversationId === undefined || typeof value.conversationId === 'string')
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
  return tabs.filter(
    (tab) =>
      tab.agentLabel === label ||
      tab.title === label ||
      tab.title.startsWith(`${label} (`),
  ).length
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
    ...(agent ? { agentId: agent.id, agentLabel: agent.label } : {}),
  }
  return {
    ...workspaces,
    [project.id]: { tabs: [...tabs, tab], activeId: id },
  }
}

export function withNewChat(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
  worktree?: string,
): Record<number, ProjectWorkspace> {
  const tabs = workspaces[project.id]?.tabs ?? []
  const id = newTerminalId()
  let number = 1
  let title = number === 1 ? 'Chat' : `Chat (${number})`
  while (tabs.some((tab) => tab.kind === 'chat' && tab.title === title)) {
    number += 1
    title = `Chat (${number})`
  }
  const tab: WorkspaceTab = {
    id,
    title,
    kind: 'chat',
    projectId: project.id,
    ...(worktree ? { worktree } : {}),
  }
  return {
    ...workspaces,
    [project.id]: { tabs: [...tabs, tab], activeId: id },
  }
}

export function withChatConversation(
  workspaces: Record<number, ProjectWorkspace>,
  projectId: number,
  tabId: string,
  conversationId: string | undefined,
  title: string,
): Record<number, ProjectWorkspace> {
  const workspace = workspaces[projectId]
  if (!workspace) return workspaces
  return {
    ...workspaces,
    [projectId]: {
      ...workspace,
      tabs: workspace.tabs.map((tab) =>
        tab.id === tabId && tab.kind === 'chat'
          ? {
              ...tab,
              ...(conversationId ? { conversationId } : { conversationId: undefined }),
              title: title.slice(0, MAX_TAB_TITLE_LENGTH),
            }
          : tab,
      ),
    },
  }
}

export function withTabTitle(
  workspaces: Record<number, ProjectWorkspace>,
  projectId: number,
  tabId: string,
  title: string,
): Record<number, ProjectWorkspace> {
  const trimmed = title.trim()
  if (trimmed.length === 0) return workspaces
  const workspace = workspaces[projectId]
  if (!workspace) return workspaces
  const tab = workspace.tabs.find((item) => item.id === tabId)
  if (!tab) return workspaces
  const bounded = trimmed.slice(0, MAX_TAB_TITLE_LENGTH)
  const nextTitle = tab.agentLabel ? `${tab.agentLabel} | ${bounded}` : bounded
  if (nextTitle === tab.title) return workspaces
  return {
    ...workspaces,
    [projectId]: {
      ...workspace,
      tabs: workspace.tabs.map((item) =>
        item.id === tabId ? { ...item, title: nextTitle } : item,
      ),
    },
  }
}

export function withOpenFile(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
  path: string,
  line?: number,
): Record<number, ProjectWorkspace> {
  const tabs = workspaces[project.id]?.tabs ?? []
  const existing = tabs.find((tab) => tab.kind === 'editor' && tab.filePath === path)
  if (existing) {
    return {
      ...workspaces,
      [project.id]: {
        tabs: tabs.map((tab) => (tab.id === existing.id ? { ...tab, line } : tab)),
        activeId: existing.id,
      },
    }
  }
  const id = newTerminalId()
  const title = path.split('/').pop() || path
  const tab: WorkspaceTab = {
    id,
    title,
    kind: 'editor',
    projectId: project.id,
    filePath: path,
    line,
  }
  return {
    ...workspaces,
    [project.id]: { tabs: [...tabs, tab], activeId: id },
  }
}

export function withWorktreeTerminal(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
  worktree: string,
): Record<number, ProjectWorkspace> {
  const tabs = workspaces[project.id]?.tabs ?? []
  const existing = tabs.find((tab) => tab.worktree === worktree)
  if (existing) {
    return {
      ...workspaces,
      [project.id]: { tabs, activeId: existing.id },
    }
  }

  return withNewTerminal(workspaces, project, { worktree })
}

export function withVSCodeTab(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
  worktree: string,
): Record<number, ProjectWorkspace> {
  const tabs = workspaces[project.id]?.tabs ?? []
  const existing = tabs.find((tab) => tab.kind === 'vscode' && tab.worktree === worktree)
  if (existing) {
    return {
      ...workspaces,
      [project.id]: { tabs, activeId: existing.id },
    }
  }

  const label = `VS Code: ${worktree}`
  const count = countByLabel(tabs, label)
  const id = newTerminalId()
  const tab: WorkspaceTab = {
    id,
    title: count === 0 ? label : `${label} (${count + 1})`,
    kind: 'vscode',
    projectId: project.id,
    worktree,
  }
  return {
    ...workspaces,
    [project.id]: { tabs: [...tabs, tab], activeId: id },
  }
}

export function withFilteredTabs(
  workspaces: Record<number, ProjectWorkspace>,
  projectId: number,
  keep: (tab: WorkspaceTab) => boolean,
): Record<number, ProjectWorkspace> {
  const workspace = workspaces[projectId]
  if (!workspace) return workspaces
  const tabs = workspace.tabs.filter(keep)
  if (tabs.length === workspace.tabs.length) return workspaces
  const activeId =
    workspace.activeId != null && tabs.some((tab) => tab.id === workspace.activeId)
      ? workspace.activeId
      : (tabs[tabs.length - 1]?.id ?? null)
  return { ...workspaces, [projectId]: { tabs, activeId } }
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
