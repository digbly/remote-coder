import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { AgentSession, Project, User } from '../lib/api'
import type { AgentDefinition } from '../lib/agents'
import type { CommandDefinition, WorkspaceTab } from '../lib/workspaceStore'
import { useViewportHeight } from '../lib/useViewportHeight'
import { MenuIcon, PanelRightIcon } from './ide/icons'
import { CommandsMenu } from './ide/CommandsMenu'
import { NewTabMenu } from './ide/NewTabMenu'
import { RightPanel } from './ide/RightPanel'
import { Sidebar } from './ide/Sidebar'
import { TAB_DOT_COLORS } from './ide/tabDisplay'

const DRAWER_MAX_WIDTH = 320
const DRAWER_GUTTER = 48

function ShellIconButton({
  label,
  onClick,
  children,
}: {
  label: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
    >
      {children}
    </button>
  )
}

interface MobileShellProps {
  user: User
  onLogout: () => void
  projectName: string | null
  projectId: number | null
  projectPending: boolean
  tabs: WorkspaceTab[]
  activeId: string | null
  onSelectTab: (tab: WorkspaceTab) => void
  onNewTerminal: (agent?: AgentDefinition) => void
  onNewChat: () => void
  onOpenSearch: () => void
  onOpenProject: (project: Project) => void
  onOpenWorktree: (project: Project, worktree: string) => void
  onOpenVSCode: (project: Project, worktree: string) => void
  onWorktreeDeleted: (projectId: number, worktree: string) => void
  onProjectDeleted: (projectId: number) => void
  activeProjectId: number | null
  activeWorktrees: Record<number, string>
  chatWorktrees: Record<number, string[]>
  onOpenFile: (path: string, line?: number) => void
  onOpenDiff: (path: string, staged: boolean, origPath?: string | null) => void
  onResumeChat: (conversationId: string, title: string) => void
  onResumeSession: (session: AgentSession) => void
  commands: CommandDefinition[]
  onRunCommand: (command: CommandDefinition) => void
  onManageCommands: () => void
  children: ReactNode
}

export function MobileShell({
  user,
  onLogout,
  projectName,
  projectId,
  projectPending,
  tabs,
  activeId,
  onSelectTab,
  onNewTerminal,
  onNewChat,
  onOpenSearch,
  onOpenProject,
  onOpenWorktree,
  onOpenVSCode,
  onWorktreeDeleted,
  onProjectDeleted,
  activeProjectId,
  activeWorktrees,
  chatWorktrees,
  onOpenFile,
  onOpenDiff,
  onResumeChat,
  onResumeSession,
  commands,
  onRunCommand,
  onManageCommands,
  children,
}: MobileShellProps) {
  const { t } = useTranslation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)
  const viewportHeight = useViewportHeight()
  const drawerRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!drawerOpen && !panelOpen) return
    const target = drawerOpen ? drawerRef.current : panelRef.current
    target?.focus()
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setDrawerOpen(false)
        setPanelOpen(false)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [drawerOpen, panelOpen])

  const drawerWidth = Math.min(DRAWER_MAX_WIDTH, window.innerWidth - DRAWER_GUTTER)

  function openProject(project: Project) {
    setDrawerOpen(false)
    onOpenProject(project)
  }

  function openWorktree(project: Project, worktree: string) {
    setDrawerOpen(false)
    onOpenWorktree(project, worktree)
  }

  function openVSCode(project: Project, worktree: string) {
    setDrawerOpen(false)
    onOpenVSCode(project, worktree)
  }

  return (
    <div
      className="flex h-[100dvh] w-full flex-col overflow-hidden bg-[var(--bg)] text-[var(--fg)]"
      style={viewportHeight != null ? { height: viewportHeight } : undefined}
    >
      <header className="flex shrink-0 flex-col border-b border-[var(--border)] bg-[var(--surface)] pt-[var(--safe-top)]">
        <div className="flex h-12 items-center gap-1 px-1.5">
          <ShellIconButton label={t('ide.menu')} onClick={() => setDrawerOpen(true)}>
            <MenuIcon width={18} height={18} />
          </ShellIconButton>
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-[var(--fg-strong)]">
            {projectName ?? t('common.appName')}
          </span>
          {projectId != null && (
            <CommandsMenu
              commands={commands}
              onRun={onRunCommand}
              onManage={onManageCommands}
            />
          )}
          {projectId != null && (
            <ShellIconButton label={t('ide.showPanel')} onClick={() => setPanelOpen(true)}>
              <PanelRightIcon width={18} height={18} />
            </ShellIconButton>
          )}
        </div>
      </header>

      <main className="relative min-h-0 flex-1 overflow-hidden">
        {projectId == null ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1 px-6 text-center">
            {projectPending ? (
              <p className="text-sm text-[var(--muted)]">{t('common.loading')}</p>
            ) : (
              <>
                <p className="text-sm text-[var(--muted)]">{t('ide.noProjectSelected')}</p>
                <p className="text-xs text-[var(--muted-4)]">{t('ide.openProjectHint')}</p>
              </>
            )}
          </div>
        ) : (
          children
        )}
      </main>

      <nav
        aria-label={t('ide.tabs')}
        className="flex shrink-0 items-stretch border-t border-[var(--border)] bg-[var(--surface)] pb-[var(--safe-bottom)]"
      >
        <div className="flex min-w-0 flex-1 items-stretch gap-1 overflow-x-auto px-1 py-1">
          {tabs.map((tab) => {
            const active = tab.id === activeId
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onSelectTab(tab)}
                title={tab.title}
                aria-current={active ? 'page' : undefined}
                className={`flex min-h-11 max-w-[10rem] shrink-0 items-center gap-2 rounded-full px-3 text-[12px] transition ${
                  active
                    ? 'bg-[var(--hover-strong)] text-[var(--fg-strong)] ring-1 ring-inset ring-[var(--border-strong-alt)]'
                    : 'text-[var(--text-2)] hover:bg-[var(--menu-hover)]'
                }`}
              >
                <span className={`h-2 w-2 shrink-0 rounded-full ${TAB_DOT_COLORS[tab.kind]}`} />
                <span className="truncate">{tab.title}</span>
              </button>
            )
          })}
        </div>
        {projectId != null && (
          <NewTabMenu placement="up" onSelect={onNewTerminal} onNewChat={onNewChat} />
        )}
      </nav>

      {drawerOpen && (
        <div
          ref={drawerRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-label={t('ide.menu')}
          className="fixed inset-0 z-40 flex outline-none"
        >
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="relative z-10 flex h-full shadow-xl shadow-black/40">
            <Sidebar
              user={user}
              onLogout={onLogout}
              onOpenProject={openProject}
              onOpenWorktree={openWorktree}
              onOpenVSCode={openVSCode}
              onWorktreeDeleted={onWorktreeDeleted}
              onProjectDeleted={onProjectDeleted}
              onOpenSearch={() => {
                setDrawerOpen(false)
                onOpenSearch()
              }}
              activeProjectId={activeProjectId}
              activeWorktrees={activeWorktrees}
              chatWorktrees={chatWorktrees}
              width={drawerWidth}
              onClose={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      )}

      {panelOpen && projectId != null && (
        <div
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-label={t('ide.panel')}
          className="fixed inset-0 z-40 flex flex-col justify-end outline-none"
        >
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setPanelOpen(false)}
            aria-hidden="true"
          />
          <div className="relative z-10 flex h-[75vh] flex-col overflow-hidden rounded-t-2xl border-t border-[var(--border)] bg-[var(--surface)] pb-[var(--safe-bottom)] [&>aside]:h-full">
            <RightPanel
              projectId={projectId}
              worktree={activeWorktrees[projectId]}
              width={window.innerWidth}
              onClose={() => setPanelOpen(false)}
              onOpenFile={onOpenFile}
              onOpenDiff={onOpenDiff}
              onResumeChat={(conversationId, title) => {
                onResumeChat(conversationId, title)
                setPanelOpen(false)
              }}
              onResumeSession={(session) => {
                onResumeSession(session)
                setPanelOpen(false)
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
