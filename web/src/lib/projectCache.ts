import { fetchProjects, fetchWorktrees, type Project, type Worktree } from './api'

// Cross-mount cache for the sidebar's project and worktree lists. The sidebar is
// unmounted whenever the mobile drawer closes, so without this every reopen
// refetches both lists and flashes a loading state. Mirrors the stale-while-
// revalidate cache used for agents in `api.ts`: serve the cached snapshot
// immediately and refresh in the background.

let projects: Project[] | null = null
let projectsRequest: Promise<Project[]> | null = null
let cacheGeneration = 0
const projectListeners = new Set<(projects: Project[]) => void>()

function publishProjects(next: Project[]): void {
  projects = next
  for (const listener of projectListeners) listener(next)
}

/** The last successfully loaded project list, or `null` before the first load. */
export function cachedProjects(): Project[] | null {
  return projects
}

export function subscribeProjects(listener: (projects: Project[]) => void): () => void {
  projectListeners.add(listener)
  return () => {
    projectListeners.delete(listener)
  }
}

export function setProjects(next: Project[]): void {
  publishProjects(next)
}

function reloadProjects(): Promise<Project[]> {
  if (projectsRequest) return projectsRequest
  const generation = cacheGeneration
  const request = (async () => {
    try {
      const list = await fetchProjects()
      if (generation === cacheGeneration) publishProjects(list)
      return list
    } finally {
      // A reset bumps the generation and nulls the request itself, so only a
      // same-generation completion may clear the in-flight slot.
      if (generation === cacheGeneration) projectsRequest = null
    }
  })()
  projectsRequest = request
  return request
}

export async function loadProjects(): Promise<Project[]> {
  if (projects) {
    void reloadProjects().catch(() => {
      /* keep serving the cached list if the refresh fails */
    })
    return projects
  }
  return reloadProjects()
}

let worktrees: Record<number, Worktree[]> | null = null
let worktreesRequest: Promise<Record<number, Worktree[]>> | null = null
const worktreeListeners = new Set<(worktrees: Record<number, Worktree[]>) => void>()

function publishWorktrees(next: Record<number, Worktree[]>): void {
  worktrees = next
  for (const listener of worktreeListeners) listener(next)
}

/** The last successfully loaded worktree lists by project, or `null` before the first load. */
export function cachedWorktrees(): Record<number, Worktree[]> | null {
  return worktrees
}

export function subscribeWorktrees(
  listener: (worktrees: Record<number, Worktree[]>) => void,
): () => void {
  worktreeListeners.add(listener)
  return () => {
    worktreeListeners.delete(listener)
  }
}

function setProjectWorktrees(projectId: number, list: Worktree[]): void {
  publishWorktrees({ ...(worktrees ?? {}), [projectId]: list })
}

export function removeProjectWorktrees(projectId: number): void {
  if (!worktrees) return
  const next = { ...worktrees }
  delete next[projectId]
  publishWorktrees(next)
}

/** Refresh one project's worktrees, keeping the previous list if the request fails. */
export async function refreshProjectWorktrees(projectId: number): Promise<void> {
  try {
    setProjectWorktrees(projectId, await fetchWorktrees(projectId))
  } catch {
    /* keep the previous list if the refresh fails */
  }
}

async function fetchAllWorktrees(list: Project[]): Promise<Record<number, Worktree[]>> {
  const entries = await Promise.all(
    list.map(async (project) => {
      try {
        return [project.id, await fetchWorktrees(project.id)] as const
      } catch {
        return [project.id, [] as Worktree[]] as const
      }
    }),
  )
  return Object.fromEntries(entries)
}

function reloadWorktrees(): Promise<Record<number, Worktree[]>> {
  if (worktreesRequest) return worktreesRequest
  const generation = cacheGeneration
  const list = projects ?? []
  const request = (async () => {
    try {
      const map = await fetchAllWorktrees(list)
      if (generation === cacheGeneration) publishWorktrees(map)
      return map
    } finally {
      // See reloadProjects: only a same-generation completion clears the slot.
      if (generation === cacheGeneration) worktreesRequest = null
    }
  })()
  worktreesRequest = request
  return request
}

export async function loadWorktrees(): Promise<Record<number, Worktree[]>> {
  if (worktrees) {
    void reloadWorktrees().catch(() => {
      /* keep serving the cached lists if the refresh fails */
    })
    return worktrees
  }
  return reloadWorktrees()
}

/**
 * Drop all cached project/worktree data. Call this when the session ends so a
 * later sign-in as a different account never renders the previous account's
 * lists; the generation bump also makes any in-flight request discard its
 * response instead of repopulating the cache after the reset.
 */
export function resetProjectCache(): void {
  cacheGeneration += 1
  projects = null
  projectsRequest = null
  worktrees = null
  worktreesRequest = null
}
