import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  fetchProjects,
  fetchWorktrees,
  type Project,
  type User,
  type Worktree,
} from '../../lib/api'
import { LanguageSwitcher } from '../LanguageSwitcher'
import {
  AutomationsIcon,
  BellIcon,
  BranchIcon,
  CloseIcon,
  CollapseIcon,
  FolderPlusIcon,
  HelpIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  TasksIcon,
} from './icons'
import { NewProjectDialog } from './NewProjectDialog'

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

function NavItem({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <button
      type="button"
      className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-sm text-[#c2c6cc] transition hover:bg-[#2a2c30] hover:text-white"
    >
      <span className="text-[#8b9099]">{icon}</span>
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
      className="rounded-md p-1 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
    >
      {children}
    </button>
  )
}

function WorktreeItem({ worktree, onOpen }: { worktree: Worktree; onOpen: () => void }) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      onClick={onOpen}
      title={worktree.path}
      className="group flex w-full flex-col gap-1 rounded-md px-2 py-1.5 text-left transition hover:bg-[#2a2c30]"
    >
      <span className="flex min-w-0 items-center gap-2">
        <span
          className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border ${
            worktree.is_primary
              ? 'border-emerald-400/70 text-emerald-400'
              : 'border-amber-400/70 text-amber-400'
          }`}
        >
          <BranchIcon width={9} height={9} />
        </span>
        <span className="truncate text-[13px] text-[#d7dae0] group-hover:text-white">
          {worktree.branch ?? worktree.name}
        </span>
        {worktree.is_primary && (
          <span className="shrink-0 rounded border border-[#3a3d42] px-1.5 py-px text-[10px] text-[#8b9099]">
            {t('ide.primary')}
          </span>
        )}
      </span>
      <span className="flex min-w-0 items-center gap-1.5 pl-[22px] text-[11px] text-[#7d828b]">
        <span className="shrink-0 rounded bg-[#2c2e33] px-1.5 py-px text-[#9aa0a8]">
          {t('ide.localHost')}
        </span>
        <span className="truncate">{worktree.name}</span>
      </span>
    </button>
  )
}

function ProjectItem({
  project,
  accent,
  active,
  worktrees,
  onOpenProject,
  onOpenWorktree,
}: {
  project: Project
  accent: string
  active: boolean
  worktrees: Worktree[] | undefined
  onOpenProject: (project: Project) => void
  onOpenWorktree: (project: Project, worktree: string) => void
}) {
  return (
    <div className="pb-1.5">
      <button
        type="button"
        onClick={() => onOpenProject(project)}
        title={project.path}
        className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] transition ${
          active ? 'bg-[#2a2c30] text-white' : 'text-[#d7dae0] hover:bg-[#24262a] hover:text-white'
        }`}
      >
        <span className={`h-3.5 w-3.5 shrink-0 rounded-sm ${accent}`} aria-hidden="true" />
        <span className="truncate font-medium">{project.name}</span>
      </button>

      {worktrees && worktrees.length > 0 && (
        <div className="mt-1 space-y-0.5 rounded-lg border border-[#2c2e33] bg-[#202124] p-1">
          {worktrees.map((worktree) => (
            <WorktreeItem
              key={worktree.path}
              worktree={worktree}
              onOpen={() => onOpenWorktree(project, worktree.name)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface SidebarProps {
  user: User
  onLogout: () => void
  onOpenProject: (project: Project) => void
  onOpenWorktree: (project: Project, worktree: string) => void
  activeProjectId: number | null
  width: number
  onClose: () => void
}

export function Sidebar({
  user,
  onLogout,
  onOpenProject,
  onOpenWorktree,
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

  return (
    <aside
      style={{ width }}
      className="flex shrink-0 flex-col bg-[#1b1c1f] text-sm"
    >
      <div className="flex items-center gap-2 px-3.5 py-3.5">
        <span className="flex gap-1.5">
          <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        </span>
        <span className="ml-1 min-w-0 truncate text-[13px] font-semibold tracking-wide text-white">
          {t('common.appName')}
        </span>
        <span className="ml-auto shrink-0">
          <IconButton label={t('ide.hideSidebar')} onClick={onClose}>
            <CloseIcon width={14} height={14} />
          </IconButton>
        </span>
      </div>

      <nav className="space-y-0.5 px-2">
        <NavItem icon={<SearchIcon />} label={t('ide.search')} />
        <NavItem icon={<TasksIcon />} label={t('ide.tasks')} />
        <NavItem icon={<AutomationsIcon />} label={t('ide.automations')} />
      </nav>

      <div className="mt-5 flex items-center justify-between px-3.5 pb-1">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-[#7d828b]">
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
          <IconButton label={t('ide.newProject')} onClick={() => setShowNewProject(true)}>
            <PlusIcon width={14} height={14} />
          </IconButton>
        </span>
      </div>

      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
        {projects === null && !error && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#7d828b]">{t('common.loading')}</p>
        )}
        {error && <p className="px-2.5 py-1.5 text-[13px] text-[#f0a9b0]">{t('ide.projectsError')}</p>}
        {projects?.length === 0 && (
          <p className="px-2.5 py-1.5 text-[13px] text-[#7d828b]">{t('ide.noProjects')}</p>
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
          />
        ))}
      </div>

      <div className="border-t border-[#2c2e33] px-2 py-2">
        <div className="flex items-center gap-2 rounded-md px-2.5 py-1.5">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-semibold uppercase text-white">
            {user.username.slice(0, 1)}
          </span>
          <span className="flex-1 truncate text-[13px] text-[#d7dae0]">{user.username}</span>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md px-1.5 py-0.5 text-[11px] text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
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
    </aside>
  )
}
