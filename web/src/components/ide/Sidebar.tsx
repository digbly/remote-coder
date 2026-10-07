import { useTranslation } from 'react-i18next'
import type { ReactNode } from 'react'
import type { User } from '../../lib/api'
import { projects } from '../../lib/mock'
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

export function Sidebar({ user, onLogout }: { user: User; onLogout: () => void }) {
  const { t } = useTranslation()

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

      <div className="flex-1 space-y-3 overflow-y-auto px-2 py-2">
        {projects.map((project) => (
          <div key={project.id}>
            <div className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] font-medium text-[#d7dae0]">
              <span className={`text-[13px] ${project.accent}`}>◆</span>
              {project.name}
            </div>
            <div className="mt-0.5 space-y-0.5 pl-3">
              {project.worktrees.map((worktree) => (
                <div
                  key={worktree.id}
                  className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] ${
                    worktree.active
                      ? 'bg-[#2a2c30] text-white'
                      : 'text-[#a4a9b1] hover:bg-[#24262a] hover:text-[#e6e8ec]'
                  }`}
                >
                  <BranchIcon width={14} height={14} className="shrink-0 text-[#7d828b]" />
                  <span className="truncate">{worktree.name}</span>
                  {worktree.primary && (
                    <span className="rounded border border-[#3a3d43] px-1 text-[10px] text-[#8b9099]">
                      {t('ide.primary')}
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-1 text-[10px] text-[#6b7078]">
                    {worktree.status && <span>{worktree.status}</span>}
                    {worktree.meta && <span>{worktree.meta}</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
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
