import { useEffect, useState } from 'react'
import { killTerminal, type Project, type User } from '../lib/api'
import {
  loadPersistedWorkspaces,
  newTerminalId,
  savePersistedWorkspaces,
  type ActiveProjectRef,
  type ProjectWorkspace,
} from '../lib/workspaceStore'
import { Sidebar } from './ide/Sidebar'
import { SourceControlPanel } from './ide/SourceControlPanel'
import { ProjectTerminal } from './ide/Terminal'
import { TopTabs } from './ide/TopTabs'

function withNewTerminal(
  workspaces: Record<number, ProjectWorkspace>,
  project: ActiveProjectRef,
): Record<number, ProjectWorkspace> {
  const tabs = workspaces[project.id]?.tabs ?? []
  const id = newTerminalId()
  const title = tabs.length === 0 ? project.name : `${project.name} (${tabs.length + 1})`
  return {
    ...workspaces,
    [project.id]: {
      tabs: [...tabs, { id, title, kind: 'terminal', projectId: project.id }],
      activeId: id,
    },
  }
}

export function IdeShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [restored] = useState(loadPersistedWorkspaces)
  const [workspaces, setWorkspaces] = useState<Record<number, ProjectWorkspace>>(
    restored.workspaces,
  )
  const [activeProject, setActiveProject] = useState<ActiveProjectRef | null>(
    restored.activeProject,
  )

  useEffect(() => {
    savePersistedWorkspaces({ activeProject, workspaces })
  }, [activeProject, workspaces])

  const activeProjectId = activeProject?.id ?? null
  const activeWorkspace = activeProjectId != null ? workspaces[activeProjectId] : undefined
  const activeTabs = activeWorkspace?.tabs ?? []
  const activeTabId = activeWorkspace?.activeId ?? null
  const allTabs = Object.values(workspaces).flatMap((workspace) => workspace.tabs)

  function openTerminal(project: ActiveProjectRef) {
    setWorkspaces((prev) => withNewTerminal(prev, project))
  }

  function openProject(project: Project) {
    setActiveProject({ id: project.id, name: project.name })
    setWorkspaces((prev) => {
      const workspace = prev[project.id]
      if (workspace && workspace.tabs.length > 0) {
        const activeId = workspace.activeId ?? workspace.tabs[workspace.tabs.length - 1].id
        return { ...prev, [project.id]: { ...workspace, activeId } }
      }
      return withNewTerminal(prev, project)
    })
  }

  function selectTab(id: string) {
    if (activeProjectId == null) return
    setWorkspaces((prev) => {
      const workspace = prev[activeProjectId]
      return workspace ? { ...prev, [activeProjectId]: { ...workspace, activeId: id } } : prev
    })
  }

  function closeTab(id: string) {
    if (activeProjectId == null) return
    const projectId = activeProjectId
    void killTerminal(projectId, id).catch(() => {
      /* the terminal may already be gone */
    })
    setWorkspaces((prev) => {
      const workspace = prev[projectId]
      if (!workspace) return prev
      const tabs = workspace.tabs.filter((tab) => tab.id !== id)
      const activeId =
        workspace.activeId === id ? (tabs[tabs.length - 1]?.id ?? null) : workspace.activeId
      return { ...prev, [projectId]: { tabs, activeId } }
    })
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0f1012] text-[#e6e8ec]">
      <Sidebar
        user={user}
        onLogout={onLogout}
        onOpenProject={openProject}
        activeProjectId={activeProjectId}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopTabs
          tabs={activeTabs}
          activeId={activeTabId}
          onSelect={selectTab}
          onClose={closeTab}
          onNew={() => activeProject && openTerminal(activeProject)}
        />
        <div className="flex min-h-0 min-w-0 flex-1">
          <div className="relative min-h-0 min-w-0 flex-1">
            {allTabs.map((tab) =>
              tab.projectId == null ? null : (
                <div
                  key={tab.id}
                  className={`absolute inset-0 ${
                    tab.id === activeTabId ? '' : 'pointer-events-none invisible'
                  }`}
                >
                  <ProjectTerminal
                    projectId={tab.projectId}
                    terminalId={tab.id}
                    active={tab.id === activeTabId}
                  />
                </div>
              ),
            )}
          </div>
          {activeProjectId != null && (
            <SourceControlPanel key={activeProjectId} projectId={activeProjectId} />
          )}
        </div>
      </div>
    </div>
  )
}
