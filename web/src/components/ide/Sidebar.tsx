import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { fetchProjects, type Project, type User } from '../../lib/api'
import { LanguageSwitcher } from '../LanguageSwitcher'
import {
  AutomationsIcon,
  BellIcon,
  BranchIcon,
  CollapseIcon,
  FolderPlusIcon,
  HelpIcon,
  MobileIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  TasksIcon,
} from './icons'

const PROJECT_ACCENTS = ['text-violet-400', 'text-sky-400', 'text-emerald-400', 'text-amber-400']

function projectAccent(index: number) {
  return PROJECT_ACCENTS[index % PROJECT_ACCENTS.length]
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

function IconButton({ label, children }: { label: string; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="rounded-md p-1 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
    >
      {children}
    </button>
  )
}

interface SidebarProps {
  user: User
  onLogout: () => void
  onOpenProject: (project: Project) => void
  activeProjectId: number | null
}

export function Sidebar({ user, onLogout, onOpenProject, activeProjectId }: SidebarProps) {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    fetchProjects()
      .then((list) => {
        if (active) setProjects(list)
      })
      .catch(() => {
        if (active) setError(true)
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-[#2c2e33] bg-[#1b1c1f] text-sm">
      <div className="flex items-center gap-2 px-3.5 py-3.5">
        <span className="flex gap-1.5">
          <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        </span>
        <span className="ml-1 text-[13px] font-semibold tracking-wide text-white">
          {t('common.appName')}
        </span>
      </div>

      <nav className="space-y-0.5 px-2">
        <NavItem icon={<SearchIcon />} label={t('ide.search')} />
        <NavItem icon={<TasksIcon />} label={t('ide.tasks')} />
        <NavItem icon={<AutomationsIcon />} label={t('ide.automations')} />
        <NavItem icon={<MobileIcon />} label={t('ide.mobile')} />
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
          <IconButton label={t('ide.newProject')}>
            <FolderPlusIcon width={14} height={14} />
          </IconButton>
          <IconButton label={t('ide.newProject')}>
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
        {projects?.map((project, index) => {
          const active = project.id === activeProjectId
          return (
            <button
              key={project.id}
              type="button"
              onClick={() => onOpenProject(project)}
              title={project.path}
              className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] transition ${
                active ? 'bg-[#2a2c30] text-white' : 'text-[#c2c6cc] hover:bg-[#24262a] hover:text-white'
              }`}
            >
              <BranchIcon width={14} height={14} className={`shrink-0 ${projectAccent(index)}`} />
              <span className="truncate">{project.name}</span>
            </button>
          )
        })}
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
          <IconButton label={t('ide.settings')}>
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
    </aside>
  )
}
