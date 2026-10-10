import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Navigate, useNavigate, useParams } from 'react-router-dom'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import {
  ChevronRightIcon,
  CommandIcon,
  GlobeIcon,
  PaletteIcon,
  SparklesIcon,
} from '../components/ide/icons'
import { ProviderSettings } from '../components/settings/ProviderSettings'
import {
  fetchAgentSettings,
  fetchAgents,
  saveAgentSetting,
  setDefaultAgent,
} from '../lib/api'
import type { AgentDefinition } from '../lib/agents'
import { useTheme, type ThemeMode } from '../lib/themeContext'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const THEME_OPTIONS: ThemeMode[] = ['light', 'dark', 'system']

function SectionNavItem({
  to,
  icon,
  label,
}: {
  to: string
  icon: ReactNode
  label: string
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-sm transition ${
          isActive
            ? 'bg-[var(--hover)] text-[var(--fg-strong)]'
            : 'text-[var(--fg-3)] hover:bg-[var(--hover-subtle)] hover:text-[var(--fg-strong)]'
        }`
      }
    >
      <span className="text-[var(--muted)]">{icon}</span>
      {label}
    </NavLink>
  )
}

function ThemeSettingRow() {
  const { t } = useTranslation()
  const { mode, setMode } = useTheme()
  const labels: Record<ThemeMode, string> = {
    light: t('settings.themeLight'),
    dark: t('settings.themeDark'),
    system: t('settings.themeSystem'),
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <p className="text-sm font-medium text-[var(--fg-strong)]">{t('settings.appearance')}</p>
      <p className="mt-0.5 text-xs text-[var(--muted-2)]">{t('settings.themeHint')}</p>
      <div
        role="group"
        aria-label={t('settings.appearance')}
        className="mt-3 inline-flex rounded-md border border-[var(--border)] bg-[var(--input)] p-0.5"
      >
        {THEME_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setMode(option)}
            aria-pressed={mode === option}
            className={`rounded px-3 py-1 text-[12px] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
              mode === option
                ? 'bg-[var(--hover)] text-[var(--fg-strong)]'
                : 'text-[var(--muted)] hover:text-[var(--fg-strong)]'
            }`}
          >
            {labels[option]}
          </button>
        ))}
      </div>
    </div>
  )
}

function LanguageSettingRow() {
  const { t } = useTranslation()
  const { resolved } = useTheme()
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <p className="text-sm font-medium text-[var(--fg-strong)]">{t('language.label')}</p>
      <p className="mt-0.5 text-xs text-[var(--muted-2)]">{t('settings.languageHint')}</p>
      <div className="mt-3">
        <LanguageSwitcher variant={resolved === 'dark' ? 'dark' : 'light'} />
      </div>
    </div>
  )
}

const inputClass =
  'mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--bg)] px-2.5 py-1.5 text-sm text-[var(--fg)] outline-none focus:border-indigo-500'

function AgentSettingRow({
  agent,
  isDefault,
  onSaved,
  onSetDefault,
}: {
  agent: AgentDefinition
  isDefault: boolean
  onSaved: (agentId: string, command: string, args: string, commitArgs: string) => void
  onSetDefault: (agentId: string) => void
}) {
  const { t } = useTranslation()
  const [command, setCommand] = useState(agent.command)
  const [args, setArgs] = useState(agent.args)
  const [commitArgs, setCommitArgs] = useState(agent.commit_args)
  const [status, setStatus] = useState<SaveStatus>('idle')

  const canSave = command.trim().length > 0 && status !== 'saving'

  async function save() {
    setStatus('saving')
    try {
      await saveAgentSetting(agent.id, command.trim(), args, commitArgs)
      onSaved(agent.id, command.trim(), args, commitArgs)
      setStatus('saved')
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-medium text-[var(--fg-strong)]">
            {agent.label}
            {isDefault && (
              <span className="rounded bg-indigo-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                {t('settings.defaultBadge')}
              </span>
            )}
          </p>
          <p className="text-xs text-[var(--muted-2)]">{agent.id}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onSetDefault(agent.id)}
            disabled={isDefault}
            className="rounded-md border border-[var(--border-strong)] bg-[var(--btn)] px-3 py-1 text-[12px] text-[var(--fg-2)] transition hover:bg-[var(--hover-alt)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('settings.setDefault')}
          </button>
          <button
            type="button"
            onClick={save}
            disabled={!canSave}
            className="rounded-md bg-[var(--hover)] px-3 py-1 text-[12px] text-[var(--fg-2)] transition hover:bg-[var(--hover-strong)] disabled:opacity-50"
          >
            {status === 'saving' ? t('settings.saving') : t('settings.save')}
          </button>
        </div>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block text-xs text-[var(--text-2)]">
          {t('settings.command')}
          <input
            value={command}
            spellCheck={false}
            onChange={(event) => {
              setCommand(event.target.value)
              setStatus('idle')
            }}
            className={inputClass}
            placeholder="claude"
          />
        </label>
        <label className="block text-xs text-[var(--text-2)]">
          {t('settings.args')}
          <input
            value={args}
            spellCheck={false}
            onChange={(event) => {
              setArgs(event.target.value)
              setStatus('idle')
            }}
            className={inputClass}
            placeholder="--model opus"
          />
        </label>
      </div>
      <label className="mt-3 block text-xs text-[var(--text-2)]">
        {t('settings.commitMessageArgs')}
        <input
          value={commitArgs}
          spellCheck={false}
          onChange={(event) => {
            setCommitArgs(event.target.value)
            setStatus('idle')
          }}
          className={inputClass}
          placeholder="--auto"
        />
      </label>
      <p className="mt-1 text-xs text-[var(--muted-2)]">{t('settings.commitMessageArgsHint')}</p>
      <p className="mt-2 h-4 text-xs">
        {status === 'saved' && <span className="text-emerald-600 dark:text-emerald-400">{t('settings.saved')}</span>}
        {status === 'error' && <span className="text-[var(--danger)]">{t('settings.saveFailed')}</span>}
      </p>
    </div>
  )
}

function AgentsSection() {
  const { t } = useTranslation()
  const [agents, setAgents] = useState<AgentDefinition[] | null>(null)
  const [defaultAgentId, setDefaultAgentId] = useState<string | null>(null)
  const [defaultError, setDefaultError] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    fetchAgents()
      .then((result) => {
        if (active) setAgents(result)
      })
      .catch(() => {
        if (active) setError(true)
      })
    fetchAgentSettings()
      .then((result) => {
        if (active) setDefaultAgentId(result.default_agent_id)
      })
      .catch(() => {
        if (active) setDefaultError(true)
      })
    return () => {
      active = false
    }
  }, [])

  function handleSaved(agentId: string, command: string, args: string, commitArgs: string) {
    setAgents((prev) =>
      prev
        ? prev.map((agent) =>
            agent.id === agentId ? { ...agent, command, args, commit_args: commitArgs } : agent,
          )
        : prev,
    )
  }

  async function handleSetDefault(agentId: string) {
    setDefaultError(false)
    try {
      const result = await setDefaultAgent(agentId)
      setDefaultAgentId(result.default_agent_id)
    } catch {
      setDefaultError(true)
    }
  }

  return (
    <>
      <h2 className="mb-1 text-sm font-semibold text-[var(--fg-strong)]">{t('settings.agents')}</h2>
      <p className="mb-5 text-sm text-[var(--text-2)]">{t('settings.description')}</p>
      {error && <p className="text-sm text-[var(--danger)]">{t('settings.loadFailed')}</p>}
      {defaultError && (
        <p className="mb-3 text-sm text-[var(--danger)]">{t('settings.defaultFailed')}</p>
      )}
      {agents === null && !error && (
        <p className="text-sm text-[var(--muted-2)]">{t('common.loading')}</p>
      )}
      {agents && (
        <div className="space-y-3">
          {agents.map((agent) => (
            <AgentSettingRow
              key={agent.id}
              agent={agent}
              isDefault={agent.id === defaultAgentId}
              onSaved={handleSaved}
              onSetDefault={handleSetDefault}
            />
          ))}
        </div>
      )}
    </>
  )
}

export function SettingsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { section } = useParams<{ section: string }>()

  const sections = [
    {
      id: 'appearance',
      icon: <PaletteIcon width={15} height={15} />,
      label: t('settings.appearance'),
      content: <ThemeSettingRow />,
    },
    {
      id: 'providers',
      icon: <SparklesIcon width={15} height={15} />,
      label: t('settings.providers'),
      content: <ProviderSettings />,
    },
    {
      id: 'agents',
      icon: <CommandIcon width={15} height={15} />,
      label: t('settings.agents'),
      content: <AgentsSection />,
    },
    {
      id: 'language',
      icon: <GlobeIcon width={15} height={15} />,
      label: t('language.label'),
      content: <LanguageSettingRow />,
    },
  ]

  const active = sections.find((item) => item.id === section)
  if (!active) return <Navigate to="/settings/appearance" replace />

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--fg)]">
      <header className="flex items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-6 py-4">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex items-center gap-1 text-sm text-[var(--text-2)] transition hover:text-[var(--fg-strong)]"
        >
          <ChevronRightIcon width={14} height={14} className="rotate-180" />
          {t('settings.back')}
        </button>
        <h1 className="text-base font-semibold text-[var(--fg-strong)]">{t('settings.title')}</h1>
      </header>
      <div className="mx-auto flex max-w-5xl gap-8 px-6 py-6">
        <aside className="w-48 shrink-0">
          <nav className="space-y-0.5">
            {sections.map((item) => (
              <SectionNavItem
                key={item.id}
                to={`/settings/${item.id}`}
                icon={item.icon}
                label={item.label}
              />
            ))}
          </nav>
        </aside>
        <main className="min-w-0 flex-1">{active.content}</main>
      </div>
    </div>
  )
}
