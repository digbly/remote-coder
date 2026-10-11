import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { killTerminal, closeBrowserSession, type Project, type User } from '../lib/api'
import type { AgentDefinition } from '../lib/agents'
import { LEFT_MAX, LEFT_MIN, RIGHT_MAX, RIGHT_MIN, type LayoutState } from '../lib/layoutStore'
import {
  withFilteredTabs,
  withNewTerminal,
  withNewChat,
  withOpenFile,
  withOpenDiff,
  withChatConversation,
  withTabTitle,
  withBrowserTab,
  type ActiveProjectRef,
  type SyncedState,
  type WorkspaceTab,
} from '../lib/workspaceStore'
import { Sidebar } from './ide/Sidebar'
import { RightPanel } from './ide/RightPanel'
import { ProjectTerminal } from './ide/Terminal'
import { ChatTab } from './ide/ChatTab'
import { BrowserTab } from './ide/BrowserTab'
import { FileEditor } from './ide/FileEditor'
import { GitDiffView } from './ide/GitDiffView'
import { TopTabs } from './ide/TopTabs'
import { TabSearchModal } from './ide/TabSearchModal'
import { VSCodePanel } from './ide/VSCodePanel'
import { ResizeHandle } from './ide/ResizeHandle'
import { PanelLeftIcon, PanelRightIcon } from './ide/icons'
import { useIsMobile } from '../lib/useMediaQuery'
import { MobileShell } from './MobileShell'

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
      className={`flex w-9 shrink-0 flex-col items-center bg-[var(--surface)] ${
        side === 'left' ? 'border-r' : 'border-l'
      } border-[var(--border)]`}
    >
      <button
        type="button"
        aria-label={label}
        title={label}
        onClick={onClick}
        className="mt-3 rounded-md p-1.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
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
  projectPending: boolean
  state: SyncedState
  update: (updater: (prev: SyncedState) => SyncedState) => void
  onOpenProject: (project: Project) => void
  onOpenWorktree: (project: Project, worktree: string) => void
  onOpenVSCode: (project: Project, worktree: string) => void
  onSelectTab: (tab: WorkspaceTab) => void
  onProjectDeleted: (projectId: number) => void
}

export function IdeShell({
  user,
  onLogout,
  activeProject,
  projectPending,
  state,
  update,
  onOpenProject,
  onOpenWorktree,
  onOpenVSCode,
  onSelectTab,
  onProjectDeleted,
}: IdeShellProps) {
  const { t } = useTranslation()
  const { workspaces, layout } = state
  const isMobile = useIsMobile()
  const [searchOpen, setSearchOpen] = useState(false)
  const [streamingChatTabs, setStreamingChatTabs] = useState<Record<string, boolean>>({})

  function updateLayout(patch: Partial<LayoutState>) {
    update((prev) => ({ ...prev, layout: { ...prev.layout, ...patch } }))
  }

  const activeProjectId = activeProject?.id ?? null
  const activeWorkspace = activeProjectId != null ? workspaces[activeProjectId] : undefined
  const activeTabs = activeWorkspace?.tabs ?? []
  const activeTabId = activeWorkspace?.activeId ?? null
  const allTabs = Object.values(workspaces).flatMap((workspace) => workspace.tabs)

  const activeWorktrees: Record<number, string> = {}
  for (const [key, workspace] of Object.entries(workspaces)) {
    const activeTab = workspace.tabs.find((tab) => tab.id === workspace.activeId)
    const worktree = activeTab?.worktree ?? workspace.activeWorktree
    if (worktree) activeWorktrees[Number(key)] = worktree
  }

  const chatWorktrees: Record<number, string[]> = {}
  for (const workspace of Object.values(workspaces)) {
    for (const tab of workspace.tabs) {
      if (tab.kind !== 'chat' || !tab.worktree || !streamingChatTabs[tab.id]) continue
      if (tab.projectId == null) continue
      const list = chatWorktrees[tab.projectId] ?? []
      if (!list.includes(tab.worktree)) list.push(tab.worktree)
      chatWorktrees[tab.projectId] = list
    }
  }

  const setChatStreaming = useCallback((tabId: string, streaming: boolean) => {
    setStreamingChatTabs((prev) => {
      if (streaming) {
        if (prev[tabId]) return prev
        return { ...prev, [tabId]: true }
      }
      if (!prev[tabId]) return prev
      const next = { ...prev }
      delete next[tabId]
      return next
    })
  }, [])

  function openTerminal(project: ActiveProjectRef, agent?: AgentDefinition) {
    update((prev) => ({ ...prev, workspaces: withNewTerminal(prev.workspaces, project, { agent }) }))
  }

  function openChat() {
    if (!activeProject) return
    const activeTab = activeTabs.find((tab) => tab.id === activeTabId)
    update((prev) => ({
      ...prev,
      workspaces: withNewChat(prev.workspaces, activeProject, activeTab?.worktree),
    }))
  }

  function openBrowser() {
    if (!activeProject) return
    update((prev) => ({
      ...prev,
      workspaces: withBrowserTab(prev.workspaces, activeProject),
    }))
  }

  function openFile(path: string, line?: number) {
    if (!activeProject) return
    update((prev) => ({
      ...prev,
      workspaces: withOpenFile(prev.workspaces, activeProject, path, line),
    }))
  }

  function openDiff(path: string, staged: boolean, origPath?: string | null, worktree?: string) {
    if (!activeProject) return
    update((prev) => ({
      ...prev,
      workspaces: withOpenDiff(prev.workspaces, activeProject, path, staged, origPath, worktree),
    }))
  }

  const setTabTitle = useCallback(
    (projectId: number, tabId: string, title: string) => {
      update((prev) => ({
        ...prev,
        workspaces: withTabTitle(prev.workspaces, projectId, tabId, title),
      }))
    },
    [update],
  )

  // Release whatever backend resources a closing tab owns (a PTY or a live
  // browser session). Best-effort: the resource may already be gone.
  function releaseTabResources(projectId: number, tab: WorkspaceTab) {
    if (tab.kind === 'terminal') {
      void killTerminal(projectId, tab.id).catch(() => {
        /* the terminal may already be gone */
      })
    } else if (tab.kind === 'browser') {
      void closeBrowserSession(projectId, tab.id).catch(() => {
        /* the session may already be gone */
      })
    }
  }

  function closeTab(id: string) {
    if (activeProjectId == null) return
    const projectId = activeProjectId
    const closing = workspaces[projectId]?.tabs.find((tab) => tab.id === id)
    if (closing) releaseTabResources(projectId, closing)
    update((prev) => ({
      ...prev,
      workspaces: withFilteredTabs(prev.workspaces, projectId, (tab) => tab.id !== id),
    }))
  }

  function closeProjectTabs(projectId: number) {
    for (const tab of workspaces[projectId]?.tabs ?? []) {
      releaseTabResources(projectId, tab)
    }
    update((prev) => {
      const next = { ...prev.workspaces }
      delete next[projectId]
      return { ...prev, workspaces: next }
    })
  }

  function handleProjectDeleted(projectId: number) {
    closeProjectTabs(projectId)
    onProjectDeleted(projectId)
  }

  function closeWorktreeTabs(projectId: number, worktree: string) {
    const removed = (workspaces[projectId]?.tabs ?? []).filter((tab) => tab.worktree === worktree)
    for (const tab of removed) {
      releaseTabResources(projectId, tab)
    }
    update((prev) => ({
      ...prev,
      workspaces: withFilteredTabs(prev.workspaces, projectId, (tab) => tab.worktree !== worktree),
    }))
  }

  const tabPanes = (
    <>
      {allTabs.map((tab) => {
        if (tab.projectId == null) return null
        const projectId = tab.projectId
        const active = tab.id === activeTabId
        return (
          <div key={tab.id} className={`absolute inset-0 ${active ? '' : 'hidden'}`}>
            {tab.kind === 'chat' ? (
              <ChatTab
                projectId={projectId}
                tabId={tab.id}
                active={active}
                conversationId={tab.conversationId}
                onStreamingChange={(streaming) => setChatStreaming(tab.id, streaming)}
                onConversationChange={(conversationId, title) =>
                  update((prev) => ({
                    ...prev,
                    workspaces: withChatConversation(
                      prev.workspaces,
                      projectId,
                      tab.id,
                      conversationId,
                      title ?? t('chat.tabTitle'),
                    ),
                  }))
                }
              />
            ) : tab.kind === 'editor' && tab.filePath ? (
              <FileEditor
                projectId={projectId}
                path={tab.filePath}
                line={tab.line}
                active={active}
              />
            ) : tab.kind === 'diff' && tab.filePath ? (
              <GitDiffView
                projectId={projectId}
                path={tab.filePath}
                staged={Boolean(tab.diffStaged)}
                origPath={tab.diffOrigPath}
                worktree={tab.worktree}
                active={active}
              />
            ) : tab.kind === 'vscode' && tab.worktree ? (
              <VSCodePanel projectId={projectId} worktree={tab.worktree} title={tab.title} />
            ) : tab.kind === 'browser' ? (
              <BrowserTab projectId={projectId} sessionId={tab.id} />
            ) : (
              <ProjectTerminal
                projectId={projectId}
                terminalId={tab.id}
                worktree={tab.worktree}
                agentId={tab.agentId}
                active={active}
                onTitle={setTabTitle}
              />
            )}
          </div>
        )
      })}
    </>
  )

  return (
    <>
      {isMobile ? (
        <MobileShell
          user={user}
          onLogout={onLogout}
          projectName={activeProject?.name ?? null}
          projectId={activeProjectId}
          projectPending={projectPending}
          tabs={activeTabs}
          activeId={activeTabId}
          onSelectTab={onSelectTab}
          onNewTerminal={(agent) => activeProject && openTerminal(activeProject, agent)}
          onNewChat={openChat}
          onOpenSearch={() => setSearchOpen(true)}
          onOpenProject={onOpenProject}
          onOpenWorktree={onOpenWorktree}
          onOpenVSCode={onOpenVSCode}
          onWorktreeDeleted={closeWorktreeTabs}
          onProjectDeleted={handleProjectDeleted}
          activeProjectId={activeProjectId}
          activeWorktrees={activeWorktrees}
          chatWorktrees={chatWorktrees}
          onOpenFile={openFile}
          onOpenDiff={openDiff}
        >
          {tabPanes}
        </MobileShell>
      ) : (
        <div className="flex h-screen w-screen overflow-hidden bg-[var(--bg)] text-[var(--fg)]">
          {layout.leftOpen ? (
            <>
              <Sidebar
                user={user}
                onLogout={onLogout}
                onOpenProject={onOpenProject}
                onOpenWorktree={onOpenWorktree}
                onOpenVSCode={onOpenVSCode}
                onWorktreeDeleted={closeWorktreeTabs}
                onProjectDeleted={handleProjectDeleted}
                onOpenSearch={() => setSearchOpen(true)}
                activeProjectId={activeProjectId}
                activeWorktrees={activeWorktrees}
                chatWorktrees={chatWorktrees}
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
              onSelect={onSelectTab}
              onClose={closeTab}
              onNew={(agent) => activeProject && openTerminal(activeProject, agent)}
              onNewChat={openChat}
              onNewBrowser={openBrowser}
            />
            <div className="flex min-h-0 min-w-0 flex-1">
              <div className="relative min-h-0 min-w-0 flex-1">
                {activeProjectId == null &&
                  (projectPending ? (
                    <div className="flex h-full w-full items-center justify-center">
                      <p className="text-sm text-[var(--muted)]">{t('common.loading')}</p>
                    </div>
                  ) : (
                    <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-center">
                      <p className="text-sm text-[var(--muted)]">{t('ide.noProjectSelected')}</p>
                      <p className="text-xs text-[var(--muted-4)]">{t('ide.openProjectHint')}</p>
                    </div>
                  ))}
                {tabPanes}
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
                      worktree={activeWorktrees[activeProjectId]}
                      width={layout.rightWidth}
                      onClose={() => updateLayout({ rightOpen: false })}
                      onOpenFile={openFile}
                      onOpenDiff={openDiff}
                      onWorktreeDeleted={closeWorktreeTabs}
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
      )}
      {searchOpen && (
        <TabSearchModal
          tabs={allTabs}
          activeId={activeTabId}
          onSelect={onSelectTab}
          onClose={() => setSearchOpen(false)}
        />
      )}
    </>
  )
}
