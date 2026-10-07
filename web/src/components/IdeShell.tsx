import { useState } from 'react'
import type { Project, User } from '../lib/api'
import { AgentPanel } from './ide/AgentPanel'
import { EditorPane } from './ide/EditorPane'
import { RightPanel } from './ide/RightPanel'
import { Sidebar } from './ide/Sidebar'
import { StatusBar } from './ide/StatusBar'
import { ProjectTerminal } from './ide/Terminal'
import { TopTabs, type WorkspaceTab } from './ide/TopTabs'

export function IdeShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [tabs, setTabs] = useState<WorkspaceTab[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [mountedIds, setMountedIds] = useState<string[]>([])

  function activate(id: string) {
    setActiveId(id)
    setMountedIds((prev) => (prev.includes(id) ? prev : [...prev, id]))
  }

  function openProject(project: Project) {
    const id = `project-${project.id}`
    setTabs((prev) =>
      prev.some((tab) => tab.id === id)
        ? prev
        : [...prev, { id, title: project.name, kind: 'terminal', projectId: project.id }],
    )
    activate(id)
  }

  function closeTab(id: string) {
    const remaining = tabs.filter((tab) => tab.id !== id)
    setTabs(remaining)
    setMountedIds((prev) => prev.filter((mountedId) => mountedId !== id))
    if (activeId === id) {
      setActiveId(remaining.at(-1)?.id ?? null)
    }
  }

  const activeTab = tabs.find((tab) => tab.id === activeId) ?? null

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0f1012] text-[#e6e8ec]">
      <Sidebar
        user={user}
        onLogout={onLogout}
        onOpenProject={openProject}
        activeProjectId={activeTab?.projectId ?? null}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopTabs tabs={tabs} activeId={activeId} onSelect={activate} onClose={closeTab} />
        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="relative min-h-0 flex-1">
              {tabs.length === 0 && <EditorPane />}
              {tabs.map((tab) =>
                tab.projectId == null || !mountedIds.includes(tab.id) ? null : (
                  <div
                    key={tab.id}
                    className={`absolute inset-0 ${
                      tab.id === activeId ? '' : 'pointer-events-none invisible'
                    }`}
                  >
                    <ProjectTerminal projectId={tab.projectId} active={tab.id === activeId} />
                  </div>
                ),
              )}
            </div>
            <AgentPanel />
          </div>
          <RightPanel />
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
