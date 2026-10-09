import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { IdeShell } from '../components/IdeShell'
import { useAuth } from '../lib/authContext'
import { fetchProject, type Project } from '../lib/api'
import { useWorkspaceSync } from '../lib/sync'
import {
  ensureWorkspace,
  withNewTerminal,
  type ActiveProjectRef,
} from '../lib/workspaceStore'

function parseProjectId(projectId: string | undefined): number | null {
  if (projectId === undefined) return null
  const id = Number(projectId)
  return Number.isInteger(id) && id > 0 ? id : null
}

export function WorkspaceLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const { state, update } = useWorkspaceSync()
  const [activeProject, setActiveProject] = useState<ActiveProjectRef | null>(null)
  const urlProjectId = parseProjectId(projectId)
  const resolvedProject =
    activeProject && activeProject.id === urlProjectId ? activeProject : null

  useEffect(() => {
    if (urlProjectId === null) {
      if (projectId !== undefined) navigate('/', { replace: true })
      return
    }
    if (activeProject?.id === urlProjectId) return

    let cancelled = false
    fetchProject(urlProjectId)
      .then((project) => {
        if (cancelled) return
        const ref = { id: project.id, name: project.name }
        setActiveProject(ref)
        update((prev) => ({ ...prev, workspaces: ensureWorkspace(prev.workspaces, ref) }))
      })
      .catch(() => {
        if (!cancelled) navigate('/', { replace: true })
      })

    return () => {
      cancelled = true
    }
  }, [projectId, urlProjectId, activeProject, update, navigate])

  if (!user) return null

  function activate(project: Project): ActiveProjectRef {
    const ref = { id: project.id, name: project.name }
    setActiveProject(ref)
    navigate(`/projects/${project.id}`)
    return ref
  }

  function openProject(project: Project) {
    const ref = activate(project)
    update((prev) => ({ ...prev, workspaces: ensureWorkspace(prev.workspaces, ref) }))
  }

  function openWorktree(project: Project, worktree: string) {
    const ref = activate(project)
    update((prev) => ({ ...prev, workspaces: withNewTerminal(prev.workspaces, ref, worktree) }))
  }

  return (
    <IdeShell
      user={user}
      onLogout={logout}
      activeProject={resolvedProject}
      state={state}
      update={update}
      onOpenProject={openProject}
      onOpenWorktree={openWorktree}
    />
  )
}
