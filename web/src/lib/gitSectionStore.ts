export const GIT_SECTIONS = ['conflicted', 'staged', 'unstaged', 'untracked'] as const

export type GitSection = (typeof GIT_SECTIONS)[number]

// Only collapsed sections are stored: a missing key means "expanded".
export type GitSectionCollapsed = Partial<Record<GitSection, boolean>>

const STORAGE_KEY = 'ide.gitSectionsCollapsed'

function isGitSection(value: unknown): value is GitSection {
  return typeof value === 'string' && (GIT_SECTIONS as readonly string[]).includes(value)
}

function readStore(): Record<string, GitSectionCollapsed> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw === null) return {}
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const result: Record<string, GitSectionCollapsed> = {}
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value !== 'object' || value === null || Array.isArray(value)) continue
      const collapsed: GitSectionCollapsed = {}
      for (const [section, flag] of Object.entries(value)) {
        if (isGitSection(section) && typeof flag === 'boolean') collapsed[section] = flag
      }
      result[key] = collapsed
    }
    return result
  } catch {
    return {}
  }
}

// Sections are remembered per project and per worktree, so switching
// branches, refreshing the status or reloading the page keeps them.
function scopeKey(projectId: number, worktree?: string): string {
  return `${projectId}:${worktree ?? ''}`
}

export function loadCollapsedSections(projectId: number, worktree?: string): GitSectionCollapsed {
  return readStore()[scopeKey(projectId, worktree)] ?? {}
}

export function saveCollapsedSections(
  projectId: number,
  worktree: string | undefined,
  collapsed: GitSectionCollapsed,
): void {
  try {
    const store = readStore()
    const key = scopeKey(projectId, worktree)
    const next: GitSectionCollapsed = {}
    for (const section of GIT_SECTIONS) {
      if (collapsed[section] === true) next[section] = true
    }
    if (Object.keys(next).length === 0) delete store[key]
    else store[key] = next
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    /* storage unavailable */
  }
}
