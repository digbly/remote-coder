import type { AgentDefinition } from './agents'
import { loadLayout, normalizeLayout, type LayoutState } from './layoutStore'

export type TabKind = 'terminal' | 'editor' | 'vscode' | 'chat' | 'diff' | 'browser'

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
  diffStaged?: boolean
  diffOrigPath?: string | null
  pinned?: boolean
  color?: string
  // Set when the user renames the tab by hand; automatic titles (PTY OSC or
  // chat conversation names) must not overwrite a name the user chose.
  customTitle?: boolean
}

export interface ProjectWorkspace {
  tabs: WorkspaceTab[]
  activeId: string | null
  // Which worktree the user is attached to. Unlike activeId it is recorded even
  // when a worktree-less tab (editor, diff) is focused, and it is persisted so
  // it survives a reload.
  activeWorktree?: string
}

export interface ActiveProjectRef {
  id: number
  name: string
}

export interface SyncedState {
  workspaces: Record<number, ProjectWorkspace>
  layout: LayoutState
  activeProjectId: number | null
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
      value.kind === 'chat' ||
      value.kind === 'browser' ||
      value.kind === 'diff') &&
    (value.projectId === undefined || typeof value.projectId === 'number') &&
    (value.worktree === undefined || typeof value.worktree === 'string') &&
    (value.agentId === undefined || typeof value.agentId === 'string') &&
    (value.agentLabel === undefined || typeof value.agentLabel === 'string') &&
    (value.filePath === undefined || typeof value.filePath === 'string') &&
    (value.line === undefined || typeof value.line === 'number') &&
    (value.conversationId === undefined || typeof value.conversationId === 'string') &&
    (value.diffStaged === undefined || typeof value.diffStaged === 'boolean') &&
    (value.diffOrigPath === undefined ||
      value.diffOrigPath === null ||
      typeof value.diffOrigPath === 'string') &&
    (value.pinned === undefined || typeof value.pinned === 'boolean') &&
    (value.color === undefined || typeof value.color === 'string') &&
    (value.customTitle === undefined || typeof value.customTitle === 'boolean')
  )
}

// Pinned tabs stay at the front of the strip; the relative order of both the
// pinned and unpinned groups is preserved.
function reorderPinned(tabs: WorkspaceTab[]): WorkspaceTab[] {
  if (!tabs.some((tab) => tab.pinned)) return tabs
  return [...tabs.filter((tab) => tab.pinned), ...tabs.filter((tab) => !tab.pinned)]
}

function parseWorkspace(value: unknown, projectId: number): ProjectWorkspace | null {
  if (!isRecord(value) || !Array.isArray(value.tabs)) return null
  const tabs = value.tabs.filter(isTab)
  if (tabs.length !== value.tabs.length) return null

  const scoped = reorderPinned(tabs.map((tab) => ({ ...tab, projectId })))
  const activeId =
    typeof value.activeId === 'string' && scoped.some((tab) => tab.id === value.activeId)
      ? value.activeId
      : (scoped[scoped.length - 1]?.id ?? null)
  const activeWorktree =
    typeof value.activeWorktree === 'string' ? value.activeWorktree : undefined
  return { tabs: scoped, activeId, ...activeWorktreePatch(activeWorktree) }
}

// Build the optional `activeWorktree` field without ever setting it to
// undefined, so spreading the result never produces an empty-looking key.
export function activeWorktreePatch(worktree: string | undefined): { activeWorktree?: string } {
  return worktree ? { activeWorktree: worktree } : {}
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
    [project.id]: {
      tabs: [...tabs, tab],
      activeId: id,
      ...activeWorktreePatch(worktree),
    },
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
    [project.id]: {
      tabs: [...tabs, tab],
      activeId: id,
      ...activeWorktreePatch(worktree),
    },
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
              title: tab.customTitle ? tab.title : title.slice(0, MAX_TAB_TITLE_LENGTH),
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
  if (tab.customTitle) return workspaces
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

export function withTabPinned(
  workspaces: Record<number, ProjectWorkspace>,
  projectId: number,
  tabId: string,
  pinned: boolean,
): Record<number, ProjectWorkspace> {
  const workspace = workspaces[projectId]
  if (!workspace) return workspaces
  const tab = workspace.tabs.find((item) => item.id === tabId)
  if (!tab || Boolean(tab.pinned) === pinned) return workspaces
  const tabs = reorderPinned(
    workspace.tabs.map((item) => (item.id === tabId ? { ...item, pinned } : item)),
  )
  return { ...workspaces, [projectId]: { ...workspace, tabs } }
}

// Move a tab to a new position. Pinned and unpinned tabs are separate groups:
// a drag across the boundary is ignored so pinned tabs always stay in front.
export function withReorderedTabs(
  workspaces: Record<number, ProjectWorkspace>,
  projectId: number,
  sourceId: string,
  targetId: string,
  position: 'before' | 'after',
): Record<number, ProjectWorkspace> {
  const workspace = workspaces[projectId]
  if (!workspace || sourceId === targetId) return workspaces
  const source = workspace.tabs.find((tab) => tab.id === sourceId)
  const target = workspace.tabs.find((tab) => tab.id === targetId)
  if (!source || !target || Boolean(source.pinned) !== Boolean(target.pinned)) return workspaces
  const next = workspace.tabs.filter((tab) => tab.id !== sourceId)
  const targetIndex = next.findIndex((tab) => tab.id === targetId)
  if (targetIndex === -1) return workspaces
  const insertAt = position === 'after' ? targetIndex + 1 : targetIndex
  next.splice(insertAt, 0, source)
  return {
    ...workspaces,
    [projectId]: { ...workspace, tabs: reorderPinned(next) },
  }
}

export function withTabColor(
  workspaces: Record<number, ProjectWorkspace>,
  projectId: number,
  tabId: string,
  color: string | undefined,
): Record<number, ProjectWorkspace> {
  const workspace = workspaces[projectId]
  if (!workspace) return workspaces
  const tab = workspace.tabs.find((item) => item.id === tabId)
  if (!tab || tab.color === color) return workspaces
  return {
    ...workspaces,
    [projectId]: {
      ...workspace,
      tabs: workspace.tabs.map((item) =>
        item.id === tabId ? { ...item, color: color ?? undefined } : item,
      ),
    },
  }
}

// Manual rename sets the title verbatim (no agent prefix) because the user
// typed exactly what they want to see.
export function withRenamedTab(
  workspaces: Record<number, ProjectWorkspace>,
  projectId: number,
  tabId: string,
  title: string,
): Record<number, ProjectWorkspace> {
  const trimmed = title.trim()
  if (trimmed.length === 0) return workspaces
  const workspace = workspaces[projectId]
  if (!workspace) return workspaces
  const bounded = trimmed.slice(0, MAX_TAB_TITLE_LENGTH)
  const tab = workspace.tabs.find((item) => item.id === tabId)
  if (!tab || (tab.title === bounded && tab.customTitle)) return workspaces
  return {
    ...workspaces,
    [projectId]: {
      ...workspace,
      tabs: workspace.tabs.map((item) =>
        item.id === tabId ? { ...item, title: bounded, customTitle: true } : item,
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
  const current = workspaces[project.id]
  const tabs = current?.tabs ?? []
  const existing = tabs.find((tab) => tab.kind === 'editor' && tab.filePath === path)
  if (existing) {
    return {
      ...workspaces,
      [project.id]: {
        tabs: tabs.map((tab) => (tab.id === existing.id ? { ...tab, line } : tab)),
        activeId: existing.id,
        ...activeWorktreePatch(current?.activeWorktree),
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
    [project.id]: {
      tabs: [...tabs, tab],
      activeId: id,
      ...activeWorktreePatch(current?.activeWorktree),
    },
  }
}

export function withOpenDiff(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
  path: string,
  staged: boolean,
  origPath?: string | null,
  worktree?: string,
): Record<number, ProjectWorkspace> {
  const current = workspaces[project.id]
  const tabs = current?.tabs ?? []
  const existing = tabs.find(
    (tab) =>
      tab.kind === 'diff' &&
      tab.filePath === path &&
      Boolean(tab.diffStaged) === staged &&
      tab.worktree === worktree,
  )
  if (existing) {
    return {
      ...workspaces,
      [project.id]: {
        tabs: tabs.map((tab) =>
          tab.id === existing.id ? { ...tab, diffOrigPath: origPath ?? null } : tab,
        ),
        activeId: existing.id,
        ...activeWorktreePatch(current?.activeWorktree),
      },
    }
  }
  const id = newTerminalId()
  const title = path.split('/').pop() || path
  const tab: WorkspaceTab = {
    id,
    title,
    kind: 'diff',
    projectId: project.id,
    filePath: path,
    diffStaged: staged,
    diffOrigPath: origPath ?? null,
    ...(worktree ? { worktree } : {}),
  }
  return {
    ...workspaces,
    [project.id]: {
      tabs: [...tabs, tab],
      activeId: id,
      ...activeWorktreePatch(current?.activeWorktree),
    },
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
      [project.id]: { tabs, activeId: existing.id, activeWorktree: worktree },
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
      [project.id]: { tabs, activeId: existing.id, activeWorktree: worktree },
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
    [project.id]: { tabs: [...tabs, tab], activeId: id, activeWorktree: worktree },
  }
}

export function withBrowserTab(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
): Record<number, ProjectWorkspace> {
  const current = workspaces[project.id]
  const tabs = current?.tabs ?? []
  const label = 'Browser'
  const count = countByLabel(tabs, label)
  const id = newTerminalId()
  const tab: WorkspaceTab = {
    id,
    title: count === 0 ? label : `${label} (${count + 1})`,
    kind: 'browser',
    projectId: project.id,
  }
  return {
    ...workspaces,
    [project.id]: {
      tabs: [...tabs, tab],
      activeId: id,
      ...activeWorktreePatch(current?.activeWorktree),
    },
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
  const activeWorktree =
    workspace.activeWorktree !== undefined &&
    tabs.some((tab) => tab.worktree === workspace.activeWorktree)
      ? workspace.activeWorktree
      : undefined
  return {
    ...workspaces,
    [projectId]: {
      tabs,
      activeId,
      ...activeWorktreePatch(activeWorktree),
    },
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
  return { workspaces: {}, layout: loadLayout(), activeProjectId: null }
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

  const activeProjectId =
    typeof value.activeProjectId === 'number' &&
    Number.isInteger(value.activeProjectId) &&
    value.activeProjectId > 0
      ? value.activeProjectId
      : null

  return {
    workspaces,
    layout: normalizeLayout(value.layout),
    activeProjectId,
  }
}
