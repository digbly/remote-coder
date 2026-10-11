import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { IdeShell } from '../components/IdeShell'
import { useAuth } from '../lib/authContext'
import { fetchProject, type Project } from '../lib/api'
import { useWorkspaceSync } from '../lib/sync'
import {
  activeWorktreePatch,
  ensureWorkspace,
  withVSCodeTab,
  withWorktreeTerminal,
  type ActiveProjectRef,
  type WorkspaceTab,
} from '../lib/workspaceStore'

function parseProjectId(value: string | null): number | null {
  if (value === null) return null
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : null
}

export function WorkspaceLayout() {
  const { user, logout } = useAuth()
  const { state, ready, update } = useWorkspaceSync()
  const [searchParams, setSearchParams] = useSearchParams()
  const [deepLinkId] = useState(() => parseProjectId(searchParams.get('project')))
  const [activeProject, setActiveProject] = useState<ActiveProjectRef | null>(null)
  const activeProjectId = state.activeProjectId
  const resolvedProject =
    activeProject && activeProject.id === activeProjectId ? activeProject : null
  const projectPending =
    !ready || (activeProjectId !== null && resolvedProject === null)

  // A project opened from a deep link is an initial intent only: fold it into the
  // synced state and drop the query param so the URL does not go stale and the
  // selection can later be cleared by any client.
  useEffect(() => {
    if (searchParams.has('project')) {
      setSearchParams({}, { replace: true })
      return
    }
    if (deepLinkId === null) return
    update((prev) =>
      prev.activeProjectId === deepLinkId ? prev : { ...prev, activeProjectId: deepLinkId },
    )
  }, [deepLinkId, searchParams, setSearchParams, update])

  useEffect(() => {
    if (activeProjectId === null) return
    if (activeProject?.id === activeProjectId) return

    let cancelled = false
    fetchProject(activeProjectId)
      .then((project) => {
        if (cancelled) return
        const ref = { id: project.id, name: project.name }
        setActiveProject(ref)
        update((prev) => ({
          ...prev,
          workspaces: ensureWorkspace(prev.workspaces, ref),
        }))
      })
      .catch(() => {
        if (cancelled) return
        // The shared project may have been deleted by another client; clear the
        // stale selection instead of retrying it forever.
        update((prev) =>
          prev.activeProjectId === activeProjectId ? { ...prev, activeProjectId: null } : prev,
        )
      })

    return () => {
      cancelled = true
    }
  }, [activeProjectId, activeProject, update])

  if (!user) return null

  function activate(project: Project): ActiveProjectRef {
    const ref = { id: project.id, name: project.name }
    setActiveProject(ref)
    update((prev) => ({ ...prev, activeProjectId: ref.id }))
    return ref
  }

  function openProject(project: Project) {
    const ref = activate(project)
    update((prev) => ({ ...prev, workspaces: ensureWorkspace(prev.workspaces, ref) }))
  }

  function openWorktree(project: Project, worktree: string) {
    const ref = activate(project)
    update((prev) => ({ ...prev, workspaces: withWorktreeTerminal(prev.workspaces, ref, worktree) }))
  }

  function openVSCode(project: Project, worktree: string) {
    const ref = activate(project)
    update((prev) => ({ ...prev, workspaces: withVSCodeTab(prev.workspaces, ref, worktree) }))
  }

  function projectDeleted(deletedId: number) {
    if (activeProject?.id !== deletedId) return
    setActiveProject(null)
    update((prev) =>
      prev.activeProjectId === deletedId ? { ...prev, activeProjectId: null } : prev,
    )
  }

  function selectTab(tab: WorkspaceTab) {
    const tabProjectId = tab.projectId
    if (tabProjectId == null) return
    update((prev) => {
      const workspace = prev.workspaces[tabProjectId]
      if (!workspace || !workspace.tabs.some((item) => item.id === tab.id)) return prev
      return {
        ...prev,
        activeProjectId: tabProjectId,
        workspaces: {
          ...prev.workspaces,
          [tabProjectId]: {
            ...workspace,
            activeId: tab.id,
            ...activeWorktreePatch(tab.worktree),
          },
        },
      }
    })
  }

  return (
    <IdeShell
      user={user}
      onLogout={logout}
      activeProject={resolvedProject}
      projectPending={projectPending}
      state={state}
      update={update}
      onOpenProject={openProject}
      onOpenWorktree={openWorktree}
      onOpenVSCode={openVSCode}
      onSelectTab={selectTab}
      onProjectDeleted={projectDeleted}
    />
  )
}
