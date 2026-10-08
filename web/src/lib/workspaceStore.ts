export type TabKind = 'terminal' | 'editor'

export interface WorkspaceTab {
  id: string
  title: string
  kind: TabKind
  projectId?: number
}

export interface ProjectWorkspace {
  tabs: WorkspaceTab[]
  activeId: string | null
}

export interface ActiveProjectRef {
  id: number
  name: string
}

export interface PersistedWorkspaces {
  activeProject: ActiveProjectRef | null
  workspaces: Record<number, ProjectWorkspace>
}

const STORAGE_KEY = 'remote-coder.workspaces'

export function newTerminalId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isProjectRef(value: unknown): value is ActiveProjectRef {
  return (
    isRecord(value) &&
    typeof value.id === 'number' &&
    Number.isInteger(value.id) &&
    typeof value.name === 'string'
  )
}

function isTab(value: unknown): value is WorkspaceTab {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.title === 'string' &&
    (value.kind === 'terminal' || value.kind === 'editor') &&
    (value.projectId === undefined || typeof value.projectId === 'number')
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

function emptyState(): PersistedWorkspaces {
  return { activeProject: null, workspaces: {} }
}

export function loadPersistedWorkspaces(): PersistedWorkspaces {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return emptyState()
    const parsed: unknown = JSON.parse(raw)
    if (!isRecord(parsed) || !isRecord(parsed.workspaces)) return emptyState()

    const workspaces: Record<number, ProjectWorkspace> = {}
    for (const [key, value] of Object.entries(parsed.workspaces)) {
      const projectId = Number(key)
      if (!Number.isInteger(projectId)) continue
      const workspace = parseWorkspace(value, projectId)
      if (workspace === null) continue
      workspaces[projectId] = workspace
    }

    return {
      activeProject: isProjectRef(parsed.activeProject) ? parsed.activeProject : null,
      workspaces,
    }
  } catch {
    return emptyState()
  }
}

export function savePersistedWorkspaces(state: PersistedWorkspaces): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    /* storage unavailable or full */
  }
}

export function clearPersistedWorkspaces(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* storage unavailable */
  }
}
