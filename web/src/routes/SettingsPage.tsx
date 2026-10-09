import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { ChevronRightIcon } from '../components/ide/icons'
import { fetchAgentSettings, saveAgentSetting } from '../lib/api'
import { AGENT_CANDIDATES, type AgentDefinition, type AgentOverride } from '../lib/agents'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const inputClass =
  'mt-1 w-full rounded-md border border-[#2c2e33] bg-[#0f1012] px-2.5 py-1.5 text-sm text-[#e6e8ec] outline-none focus:border-indigo-500'

function AgentSettingRow({
  agent,
  override,
  onSaved,
}: {
  agent: AgentDefinition
  override?: AgentOverride
  onSaved: (agentId: string, command: string, args: string) => void
}) {
  const { t } = useTranslation()
  const [command, setCommand] = useState(override?.command ?? agent.command)
  const [args, setArgs] = useState(override?.args ?? agent.args)
  const [status, setStatus] = useState<SaveStatus>('idle')

  const canSave = command.trim().length > 0 && status !== 'saving'

  async function save() {
    setStatus('saving')
    try {
      await saveAgentSetting(agent.id, command.trim(), args)
      onSaved(agent.id, command.trim(), args)
      setStatus('saved')
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="rounded-lg border border-[#2c2e33] bg-[#1b1c1f] p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-white">{agent.label}</p>
          <p className="text-xs text-[#7d828b]">{agent.id}</p>
        </div>
        <button
          type="button"
          onClick={save}
          disabled={!canSave}
          className="rounded-md bg-[#2a2c30] px-3 py-1 text-[12px] text-[#d7dae0] transition hover:bg-[#33363b] disabled:opacity-50"
        >
          {status === 'saving' ? t('settings.saving') : t('settings.save')}
        </button>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block text-xs text-[#9aa0a8]">
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
        <label className="block text-xs text-[#9aa0a8]">
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
      <p className="mt-2 h-4 text-xs">
        {status === 'saved' && <span className="text-emerald-400">{t('settings.saved')}</span>}
        {status === 'error' && <span className="text-[#f0a9b0]">{t('settings.saveFailed')}</span>}
      </p>
    </div>
  )
}

export function SettingsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [overrides, setOverrides] = useState<Record<string, AgentOverride> | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    fetchAgentSettings()
      .then((settings) => {
        if (!active) return
        const map: Record<string, AgentOverride> = {}
        for (const setting of settings) {
          map[setting.agent_id] = { command: setting.command, args: setting.args }
        }
        setOverrides(map)
      })
      .catch(() => {
        if (active) setError(true)
      })
    return () => {
      active = false
    }
  }, [])

  function handleSaved(agentId: string, command: string, args: string) {
    setOverrides((prev) => ({ ...(prev ?? {}), [agentId]: { command, args } }))
  }

  return (
    <div className="min-h-screen bg-[#0f1012] text-[#e6e8ec]">
      <header className="flex items-center gap-3 border-b border-[#2c2e33] bg-[#1b1c1f] px-6 py-4">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex items-center gap-1 text-sm text-[#9aa0a8] transition hover:text-white"
        >
          <ChevronRightIcon width={14} height={14} className="rotate-180" />
          {t('settings.back')}
        </button>
        <h1 className="text-base font-semibold text-white">{t('settings.title')}</h1>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-6">
        <p className="mb-5 text-sm text-[#9aa0a8]">{t('settings.description')}</p>
        {error && <p className="text-sm text-[#f0a9b0]">{t('settings.loadFailed')}</p>}
        {overrides === null && !error && (
          <p className="text-sm text-[#7d828b]">{t('common.loading')}</p>
        )}
        {overrides && (
          <div className="space-y-3">
            {AGENT_CANDIDATES.map((agent) => (
              <AgentSettingRow
                key={agent.id}
                agent={agent}
                override={overrides[agent.id]}
                onSaved={handleSaved}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
