import { useTranslation } from 'react-i18next'
import { killTerminal, type Project, type User } from '../lib/api'
import type { AgentDefinition } from '../lib/agents'
import { LEFT_MAX, LEFT_MIN, RIGHT_MAX, RIGHT_MIN, type LayoutState } from '../lib/layoutStore'
import {
  withNewTerminal,
  withOpenFile,
  type ActiveProjectRef,
  type SyncedState,
} from '../lib/workspaceStore'
import { Sidebar } from './ide/Sidebar'
import { RightPanel } from './ide/RightPanel'
import { ProjectTerminal } from './ide/Terminal'
import { FileEditor } from './ide/FileEditor'
import { TopTabs } from './ide/TopTabs'
import { VSCodePanel } from './ide/VSCodePanel'
import { ResizeHandle } from './ide/ResizeHandle'
import { PanelLeftIcon, PanelRightIcon } from './ide/icons'

function SidebarRail({
  side,
  label,
  onClick,
}: {
  side: 'left' | 'right'
  label: string
  onClick: () => void
}) {
  return (
    <div
      className={`flex w-9 shrink-0 flex-col items-center bg-[#1b1c1f] ${
        side === 'left' ? 'border-r' : 'border-l'
      } border-[#2c2e33]`}
    >
      <button
        type="button"
        aria-label={label}
        title={label}
        onClick={onClick}
        className="mt-3 rounded-md p-1.5 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
      >
        {side === 'left' ? (
          <PanelLeftIcon width={16} height={16} />
        ) : (
          <PanelRightIcon width={16} height={16} />
        )}
      </button>
    </div>
  )
}

interface IdeShellProps {
  user: User
  onLogout: () => void
  activeProject: ActiveProjectRef | null
  state: SyncedState
  update: (updater: (prev: SyncedState) => SyncedState) => void
  onOpenProject: (project: Project) => void
  onOpenWorktree: (project: Project, worktree: string) => void
  onOpenVSCode: (project: Project, worktree: string) => void
}

export function IdeShell({
  user,
  onLogout,
  activeProject,
  state,
  update,
  onOpenProject,
  onOpenWorktree,
  onOpenVSCode,
}: IdeShellProps) {
  const { t } = useTranslation()
  const { workspaces, layout } = state

  function updateLayout(patch: Partial<LayoutState>) {
    update((prev) => ({ ...prev, layout: { ...prev.layout, ...patch } }))
  }

  const activeProjectId = activeProject?.id ?? null
  const activeWorkspace = activeProjectId != null ? workspaces[activeProjectId] : undefined
  const activeTabs = activeWorkspace?.tabs ?? []
  const activeTabId = activeWorkspace?.activeId ?? null
  const allTabs = Object.values(workspaces).flatMap((workspace) => workspace.tabs)

  function openTerminal(project: ActiveProjectRef, agent?: AgentDefinition) {
    update((prev) => ({ ...prev, workspaces: withNewTerminal(prev.workspaces, project, { agent }) }))
  }

  function openFile(path: string) {
    if (!activeProject) return
    update((prev) => ({ ...prev, workspaces: withOpenFile(prev.workspaces, activeProject, path) }))
  }

  function selectTab(id: string) {
    if (activeProjectId == null) return
    update((prev) => {
      const workspace = prev.workspaces[activeProjectId]
      if (!workspace) return prev
      return {
        ...prev,
        workspaces: { ...prev.workspaces, [activeProjectId]: { ...workspace, activeId: id } },
      }
    })
  }

  function closeTab(id: string) {
    if (activeProjectId == null) return
    const projectId = activeProjectId
    const closing = workspaces[projectId]?.tabs.find((tab) => tab.id === id)
    if (closing?.kind === 'terminal') {
      void killTerminal(projectId, id).catch(() => {
        /* the terminal may already be gone */
      })
    }
    update((prev) => {
      const workspace = prev.workspaces[projectId]
      if (!workspace) return prev
      const tabs = workspace.tabs.filter((tab) => tab.id !== id)
      const activeId =
        workspace.activeId === id ? (tabs[tabs.length - 1]?.id ?? null) : workspace.activeId
      return { ...prev, workspaces: { ...prev.workspaces, [projectId]: { tabs, activeId } } }
    })
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0f1012] text-[#e6e8ec]">
      {layout.leftOpen ? (
        <>
          <Sidebar
            user={user}
            onLogout={onLogout}
            onOpenProject={onOpenProject}
            onOpenWorktree={onOpenWorktree}
            onOpenVSCode={onOpenVSCode}
            activeProjectId={activeProjectId}
            width={layout.leftWidth}
            onClose={() => updateLayout({ leftOpen: false })}
          />
          <ResizeHandle
            side="left"
            width={layout.leftWidth}
            min={LEFT_MIN}
            max={LEFT_MAX}
            onResize={(leftWidth) => updateLayout({ leftWidth })}
            label={t('ide.resizeSidebar')}
          />
        </>
      ) : (
        <SidebarRail
          side="left"
          label={t('ide.showSidebar')}
          onClick={() => updateLayout({ leftOpen: true })}
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopTabs
          tabs={activeTabs}
          activeId={activeTabId}
          onSelect={selectTab}
          onClose={closeTab}
          onNew={(agent) => activeProject && openTerminal(activeProject, agent)}
        />
        <div className="flex min-h-0 min-w-0 flex-1">
          <div className="relative min-h-0 min-w-0 flex-1">
            {activeProjectId == null && (
              <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-center">
                <p className="text-sm text-[#8b9099]">{t('ide.noProjectSelected')}</p>
                <p className="text-xs text-[#5f646c]">{t('ide.openProjectHint')}</p>
              </div>
            )}
            {allTabs.map((tab) => {
              if (tab.projectId == null) return null
              const active = tab.id === activeTabId
              return (
                <div
                  key={tab.id}
                  className={`absolute inset-0 ${
                    active ? '' : 'pointer-events-none invisible'
                  }`}
                >
                  {tab.kind === 'editor' && tab.filePath ? (
                    <FileEditor projectId={tab.projectId} path={tab.filePath} active={active} />
                  ) : tab.kind === 'vscode' && tab.worktree ? (
                    <VSCodePanel
                      projectId={tab.projectId}
                      worktree={tab.worktree}
                      title={tab.title}
                    />
                  ) : (
                    <ProjectTerminal
                      projectId={tab.projectId}
                      terminalId={tab.id}
                      worktree={tab.worktree}
                      agentCommand={tab.agentCommand}
                      active={active}
                    />
                  )}
                </div>
              )
            })}
          </div>
          {activeProjectId != null &&
            (layout.rightOpen ? (
              <>
                <ResizeHandle
                  side="right"
                  width={layout.rightWidth}
                  min={RIGHT_MIN}
                  max={RIGHT_MAX}
                  onResize={(rightWidth) => updateLayout({ rightWidth })}
                  label={t('ide.resizePanel')}
                />
                <RightPanel
                  key={activeProjectId}
                  projectId={activeProjectId}
                  width={layout.rightWidth}
                  onClose={() => updateLayout({ rightOpen: false })}
                  onOpenFile={openFile}
                />
              </>
            ) : (
              <SidebarRail
                side="right"
                label={t('ide.showPanel')}
                onClick={() => updateLayout({ rightOpen: true })}
              />
            ))}
        </div>
      </div>
    </div>
  )
}
