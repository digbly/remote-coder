import { useRef, useState } from 'react'
import type { Project, User } from '../lib/api'
import { Sidebar } from './ide/Sidebar'
import { SourceControlPanel } from './ide/SourceControlPanel'
import { ProjectTerminal } from './ide/Terminal'
import { TopTabs, type WorkspaceTab } from './ide/TopTabs'

interface ProjectWorkspace {
  tabs: WorkspaceTab[]
  activeId: string | null
}

export function IdeShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [workspaces, setWorkspaces] = useState<Record<number, ProjectWorkspace>>({})
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const tabSeq = useRef(0)

  const activeProjectId = activeProject?.id ?? null
  const activeWorkspace = activeProjectId != null ? workspaces[activeProjectId] : undefined
  const activeTabs = activeWorkspace?.tabs ?? []
  const activeTabId = activeWorkspace?.activeId ?? null
  const allTabs = Object.values(workspaces).flatMap((workspace) => workspace.tabs)

  function openTerminal(project: Project) {
    tabSeq.current += 1
    const id = `project-${project.id}-${tabSeq.current}`
    setWorkspaces((prev) => {
      const tabs = prev[project.id]?.tabs ?? []
      const title = tabs.length === 0 ? project.name : `${project.name} (${tabs.length + 1})`
      return {
        ...prev,
        [project.id]: {
          tabs: [...tabs, { id, title, kind: 'terminal', projectId: project.id }],
          activeId: id,
        },
      }
    })
  }

  function openProject(project: Project) {
    tabSeq.current += 1
    const id = `project-${project.id}-${tabSeq.current}`
    setActiveProject(project)
    setWorkspaces((prev) => {
      const workspace = prev[project.id]
      if (workspace && workspace.tabs.length > 0) {
        const activeId = workspace.activeId ?? workspace.tabs[workspace.tabs.length - 1].id
        return { ...prev, [project.id]: { ...workspace, activeId } }
      }
      return {
        ...prev,
        [project.id]: {
          tabs: [{ id, title: project.name, kind: 'terminal', projectId: project.id }],
          activeId: id,
        },
      }
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
    setWorkspaces((prev) => {
      const workspace = prev[activeProjectId]
      if (!workspace) return prev
      const tabs = workspace.tabs.filter((tab) => tab.id !== id)
      const activeId =
        workspace.activeId === id ? (tabs[tabs.length - 1]?.id ?? null) : workspace.activeId
      return { ...prev, [activeProjectId]: { tabs, activeId } }
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
                  <ProjectTerminal projectId={tab.projectId} active={tab.id === activeTabId} />
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
