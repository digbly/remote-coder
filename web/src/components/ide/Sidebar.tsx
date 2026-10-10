import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  deleteWorktree,
  fetchProjects,
  fetchWorktrees,
  vscodeUrl,
  type Project,
  type User,
  type Worktree,
} from '../../lib/api'
import { LanguageSwitcher } from '../LanguageSwitcher'
import {
  BellIcon,
  BranchIcon,
  CloseIcon,
  CodeIcon,
  CollapseIcon,
  ExternalLinkIcon,
  FolderPlusIcon,
  HelpIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  TerminalIcon,
  TrashIcon,
} from './icons'
import { NewProjectDialog } from './NewProjectDialog'
import { NewWorktreeDialog } from './NewWorktreeDialog'

const PROJECT_ACCENTS = ['bg-violet-400', 'bg-sky-400', 'bg-emerald-400', 'bg-amber-400']

function projectAccent(index: number) {
  return PROJECT_ACCENTS[index % PROJECT_ACCENTS.length]
}

async function loadWorktrees(projects: Project[]): Promise<Record<number, Worktree[]>> {
  const entries = await Promise.all(
    projects.map(async (project) => {
      try {
        return [project.id, await fetchWorktrees(project.id)] as const
      } catch {
        return [project.id, [] as Worktree[]] as const
      }
    }),
  )
  return Object.fromEntries(entries)
}

function NavItem({ icon, label, onClick }: { icon: ReactNode; label: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-sm text-[var(--fg-3)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
    >
      <span className="text-[var(--muted)]">{icon}</span>
      {label}
    </button>
  )
}

function IconButton({
  label,
  children,
  onClick,
}: {
  label: string
  children: ReactNode
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="rounded-md p-1 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
    >
      {children}
    </button>
  )
}

function WorktreeItem({
  worktree,
  onOpen,
  onOpenVSCode,
  onContextMenu,
}: {
  worktree: Worktree
  onOpen: () => void
  onOpenVSCode: () => void
  onContextMenu: (x: number, y: number) => void
}) {
  const { t } = useTranslation()
  return (
    <div
      title={worktree.path}
      onContextMenu={(event) => {
        event.preventDefault()
        onContextMenu(event.clientX, event.clientY)
      }}
      className="group flex w-full items-center rounded-md px-2 py-1.5 transition hover:bg-[var(--hover)]"
    >
      <button
        type="button"
        onClick={onOpen}
        className="flex min-w-0 flex-1 flex-col gap-1 text-left"
      >
        <span className="flex min-w-0 items-center gap-2">
          <span
            className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border ${
              worktree.is_primary
                ? 'border-emerald-400/70 text-emerald-600 dark:text-emerald-400'
                : 'border-amber-400/70 text-amber-600 dark:text-amber-400'
            }`}
          >
            <BranchIcon width={9} height={9} />
          </span>
          <span className="truncate text-[13px] text-[var(--fg-2)] group-hover:text-[var(--fg-strong)]">
            {worktree.branch ?? worktree.name}
          </span>
          {worktree.is_primary && (
            <span className="shrink-0 rounded border border-[var(--border-strong-alt)] px-1.5 py-px text-[10px] text-[var(--muted)]">
              {t('ide.primary')}
            </span>
          )}
        </span>
        <span className="flex min-w-0 items-center gap-1.5 pl-[22px] text-[11px] text-[var(--muted-2)]">
          <span className="shrink-0 rounded bg-[var(--chip)] px-1.5 py-px text-[var(--text-2)]">
            {t('ide.localHost')}
          </span>
          <span className="truncate">{worktree.name}</span>
        </span>
      </button>
      <button
        type="button"
        aria-label={t('ide.openInVSCode')}
        title={t('ide.openInVSCode')}
        onClick={onOpenVSCode}
        className="ml-1 shrink-0 rounded p-1 text-[var(--muted)] opacity-0 transition hover:bg-[var(--hover-strong)] hover:text-[var(--fg-strong)] group-hover:opacity-100 focus:opacity-100"
      >
        <CodeIcon width={14} height={14} />
      </button>
    </div>
  )
}

function ProjectItem({
  project,
  accent,
  active,
  worktrees,
  onOpenProject,
  onOpenWorktree,
  onOpenVSCode,
  onOpenWorktreeDialog,
  onWorktreeContextMenu,
}: {
  project: Project
  accent: string
  active: boolean
  worktrees: Worktree[] | undefined
  onOpenProject: (project: Project) => void
  onOpenWorktree: (project: Project, worktree: string) => void
  onOpenVSCode: (project: Project, worktree: string) => void
  onOpenWorktreeDialog: (project: Project) => void
  onWorktreeContextMenu: (worktree: Worktree, x: number, y: number) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="pb-1.5">
      <div
        className={`group flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition ${
          active ? 'bg-[var(--hover)] text-[var(--fg-strong)]' : 'text-[var(--fg-2)] hover:bg-[var(--hover-subtle)] hover:text-[var(--fg-strong)]'
        }`}
      >
        <button
          type="button"
          onClick={() => onOpenProject(project)}
          title={project.path}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <span className={`h-3.5 w-3.5 shrink-0 rounded-sm ${accent}`} aria-hidden="true" />
          <span className="truncate font-medium">{project.name}</span>
        </button>
        <button
          type="button"
          aria-label={t('ide.createWorktree')}
          title={t('ide.createWorktree')}
          onClick={() => onOpenWorktreeDialog(project)}
          className="shrink-0 rounded p-1 text-[var(--muted)] opacity-0 transition hover:bg-[var(--hover-strong)] hover:text-[var(--fg-strong)] group-hover:opacity-100 focus:opacity-100"
        >
          <PlusIcon width={13} height={13} />
        </button>
      </div>

      {worktrees && worktrees.length > 0 && (
        <div className="mt-1 space-y-0.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-1">
          {worktrees.map((worktree) => (
            <WorktreeItem
              key={worktree.path}
              worktree={worktree}
              onOpen={() => onOpenWorktree(project, worktree.name)}
              onOpenVSCode={() => onOpenVSCode(project, worktree.name)}
              onContextMenu={(x, y) => onWorktreeContextMenu(worktree, x, y)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface WorktreeMenu {
  x: number
  y: number
  project: Project
  worktree: Worktree
}

const MENU_WIDTH = 208
const MENU_HEIGHT = 132
const MENU_MARGIN = 8

interface SidebarProps {
  user: User
  onLogout: () => void
  onOpenProject: (project: Project) => void
  onOpenWorktree: (project: Project, worktree: string) => void
  onOpenVSCode: (project: Project, worktree: string) => void
  onOpenSearch: () => void
  activeProjectId: number | null
  width: number
  onClose: () => void
}

export function Sidebar({
  user,
  onLogout,
  onOpenProject,
  onOpenWorktree,
  onOpenVSCode,
  onOpenSearch,
  activeProjectId,
  width,
  onClose,
}: SidebarProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [worktrees, setWorktrees] = useState<Record<number, Worktree[]>>({})
  const [error, setError] = useState(false)
  const [showNewProject, setShowNewProject] = useState(false)
  const [worktreeTarget, setWorktreeTarget] = useState<Project | null>(null)
  const [menu, setMenu] = useState<WorktreeMenu | null>(null)
  const [menuError, setMenuError] = useState<string | null>(null)

  useEffect(() => {
    if (!menu) return
    function close() {
      setMenu(null)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenu(null)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [menu])

  useEffect(() => {
    let active = true
    fetchProjects()
      .then(async (list) => {
        if (!active) return
        setProjects(list)
        const loaded = await loadWorktrees(list)
        if (active) setWorktrees(loaded)
      })
      .catch(() => {
        if (active) setError(true)
      })
    return () => {
      active = false
    }
  }, [])

  function handleCreated(project: Project) {
    setShowNewProject(false)
    setError(false)
    setProjects((prev) => (prev ? [project, ...prev] : [project]))
    fetchWorktrees(project.id)
      .then((list) => setWorktrees((prev) => ({ ...prev, [project.id]: list })))
      .catch(() => setWorktrees((prev) => ({ ...prev, [project.id]: [] })))
    onOpenProject(project)
  }

  function handleWorktreeCreated(project: Project, worktree: Worktree) {
    setWorktreeTarget(null)
    fetchWorktrees(project.id)
      .then((list) => setWorktrees((prev) => ({ ...prev, [project.id]: list })))
      .catch(() => setWorktrees((prev) => ({ ...prev, [project.id]: prev[project.id] ?? [] })))
    onOpenWorktree(project, worktree.name)
  }

  function openVSCodeNewTab(project: Project, worktree: string) {
    window.open(vscodeUrl(project.id, worktree), '_blank', 'noopener,noreferrer')
  }

  function openWorktreeMenu(project: Project, worktree: Worktree, x: number, y: number) {
    setMenuError(null)
    const maxX = Math.max(MENU_MARGIN, window.innerWidth - MENU_WIDTH - MENU_MARGIN)
    const maxY = Math.max(MENU_MARGIN, window.innerHeight - MENU_HEIGHT - MENU_MARGIN)
    setMenu({
      x: Math.min(x, maxX),
      y: Math.min(y, maxY),
      project,
      worktree,
    })
  }

  function runMenuAction(action: (project: Project, worktree: string) => void) {
    if (!menu) return
    const current = menu
    setMenu(null)
    action(current.project, current.worktree.name)
  }

  function handleDeleteWorktree() {
    if (!menu) return
    const current = menu
    setMenu(null)
    if (current.worktree.is_primary) return
    if (
      !window.confirm(
        t('ide.deleteWorktreeConfirm', { name: current.worktree.branch ?? current.worktree.name }),
      )
    ) {
      return
    }
    setMenuError(null)
    deleteWorktree(current.project.id, current.worktree.name)
      .then(() => fetchWorktrees(current.project.id))
      .then((list) => setWorktrees((prev) => ({ ...prev, [current.project.id]: list })))
      .catch((err) => {
        setMenuError(err instanceof Error ? err.message : t('ide.deleteWorktreeFailed'))
      })
  }

  return (
    <aside
      style={{ width }}
      className="flex shrink-0 flex-col bg-[var(--surface)] text-sm"
    >
      <div className="flex items-center gap-2 px-3.5 py-3.5">
        <span className="ml-1 min-w-0 truncate text-[13px] font-semibold tracking-wide text-[var(--fg-strong)]">
          {t('common.appName')}
        </span>
        <span className="ml-auto shrink-0">
          <IconButton label={t('ide.hideSidebar')} onClick={onClose}>
            <CloseIcon width={14} height={14} />
          </IconButton>
        </span>
      </div>

      <nav className="space-y-0.5 px-2">
        <NavItem icon={<SearchIcon />} label={t('ide.search')} onClick={onOpenSearch} />
        
      </nav>

      <div className="mt-5 flex items-center justify-between px-3.5 pb-1">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-2)]">
          {t('ide.projects')}
        </span>
        <span className="flex items-center gap-0.5">
          <IconButton label={t('ide.notifications')}>
            <BellIcon width={14} height={14} />
          </IconButton>
          <IconButton label={t('ide.projects')}>
            <CollapseIcon width={14} height={14} />
          </IconButton>
          <IconButton label={t('ide.newProject')} onClick={() => setShowNewProject(true)}>
            <FolderPlusIcon width={14} height={14} />
          </IconButton>
        </span>
      </div>

      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
        {menuError && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--danger)]">{menuError}</p>
        )}
        {projects === null && !error && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">{t('common.loading')}</p>
        )}
        {error && <p className="px-2.5 py-1.5 text-[13px] text-[var(--danger)]">{t('ide.projectsError')}</p>}
        {projects?.length === 0 && (
          <p className="px-2.5 py-1.5 text-[13px] text-[var(--muted-2)]">{t('ide.noProjects')}</p>
        )}
        {projects?.map((project, index) => (
          <ProjectItem
            key={project.id}
            project={project}
            accent={projectAccent(index)}
            active={project.id === activeProjectId}
            worktrees={worktrees[project.id]}
            onOpenProject={onOpenProject}
            onOpenWorktree={onOpenWorktree}
            onOpenVSCode={onOpenVSCode}
            onOpenWorktreeDialog={setWorktreeTarget}
            onWorktreeContextMenu={(worktree, x, y) =>
              openWorktreeMenu(project, worktree, x, y)
            }
          />
        ))}
      </div>

      <div className="border-t border-[var(--border)] px-2 py-2">
        <div className="flex items-center gap-2 rounded-md px-2.5 py-1.5">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-semibold uppercase text-white">
            {user.username.slice(0, 1)}
          </span>
          <span className="flex-1 truncate text-[13px] text-[var(--fg-2)]">{user.username}</span>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md px-1.5 py-0.5 text-[11px] text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
          >
            {t('ide.signOut')}
          </button>
        </div>
        <div className="mt-1 flex items-center gap-1 px-1">
          <IconButton label={t('ide.settings')} onClick={() => navigate('/settings')}>
            <SettingsIcon />
          </IconButton>
          <IconButton label={t('ide.help')}>
            <HelpIcon />
          </IconButton>
          <div className="ml-auto">
            <LanguageSwitcher variant="dark" />
          </div>
        </div>
      </div>

      {showNewProject && (
        <NewProjectDialog
          onClose={() => setShowNewProject(false)}
          onCreated={handleCreated}
        />
      )}

      {worktreeTarget && (
        <NewWorktreeDialog
          project={worktreeTarget}
          onClose={() => setWorktreeTarget(null)}
          onCreated={(worktree) => handleWorktreeCreated(worktreeTarget, worktree)}
        />
      )}

      {menu && (
        <div
          role="menu"
          style={{ top: menu.y, left: menu.x }}
          onMouseDown={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.preventDefault()}
          className="fixed z-30 w-52 overflow-hidden rounded-md border border-[var(--border)] bg-[var(--surface)] py-1 text-[12px] shadow-xl shadow-black/40"
        >
          <p className="truncate px-3 py-1 text-[10px] uppercase tracking-wide text-[var(--muted-3)]">
            {menu.worktree.name}
          </p>
          <button
            type="button"
            role="menuitem"
            onClick={() => runMenuAction(onOpenWorktree)}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--fg-2)] hover:bg-[var(--active)]"
          >
            <TerminalIcon width={13} height={13} />
            {t('ide.openTerminal')}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => runMenuAction(onOpenVSCode)}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--fg-2)] hover:bg-[var(--active)]"
          >
            <CodeIcon width={13} height={13} />
            {t('ide.openInVSCode')}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => runMenuAction(openVSCodeNewTab)}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--fg-2)] hover:bg-[var(--active)]"
          >
            <ExternalLinkIcon width={13} height={13} />
            {t('ide.openInNewTab')}
          </button>
          {!menu.worktree.is_primary && (
            <>
              <div className="my-1 border-t border-[var(--border)]" />
              <button
                type="button"
                role="menuitem"
                onClick={handleDeleteWorktree}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--danger)] hover:bg-[var(--active)]"
              >
                <TrashIcon width={13} height={13} />
                {t('ide.deleteWorktree')}
              </button>
            </>
          )}
        </div>
      )}
    </aside>
  )
}
