import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createAIProvider,
  deleteAIProvider,
  fetchAIProviderModels,
  fetchAIProviders,
  updateAIProvider,
  type AIProvider,
  type AIProviderKind,
  type AIProviderModel,
} from '../../lib/api'

const inputClass =
  'mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--bg)] px-2.5 py-1.5 text-sm text-[var(--fg)] outline-none focus:border-indigo-500'

const PROVIDER_KINDS: AIProviderKind[] = ['openai', 'anthropic', 'gemini']
const PROVIDER_KIND_LABELS = {
  openai: 'settings.providerOpenAI',
  anthropic: 'settings.providerAnthropic',
  gemini: 'settings.providerGemini',
} as const

function ProviderCard({
  provider,
  canManage,
  onUpdate,
  onDelete,
}: {
  provider: AIProvider
  canManage: boolean
  onUpdate: (provider: AIProvider) => void
  onDelete: (providerId: number) => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(provider.name)
  const [apiKey, setApiKey] = useState('')
  const [models, setModels] = useState<AIProviderModel[] | null>(null)
  const [busy, setBusy] = useState<'save' | 'test' | 'delete' | null>(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  async function save() {
    if (!name.trim()) return
    setBusy('save')
    setError('')
    setSaved(false)
    try {
      const updated = await updateAIProvider(
        provider.id,
        { name: name.trim(), ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}) },
        provider.shared,
      )
      setName(updated.name)
      setApiKey('')
      setSaved(true)
      onUpdate(updated)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('settings.providerActionFailed'))
    } finally {
      setBusy(null)
    }
  }

  async function testConnection() {
    setBusy('test')
    setError('')
    setModels(null)
    try {
      setModels(await fetchAIProviderModels(provider.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('settings.providerActionFailed'))
    } finally {
      setBusy(null)
    }
  }

  async function remove() {
    if (!window.confirm(t('settings.providerDeleteConfirm', { name: provider.name }))) return
    setBusy('delete')
    setError('')
    try {
      await deleteAIProvider(provider.id, provider.shared)
      onDelete(provider.id)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('settings.providerActionFailed'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <article className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium text-[var(--fg-strong)]">{provider.name}</h3>
          <span className="rounded bg-[var(--chip)] px-1.5 py-0.5 text-[10px] uppercase text-[var(--text-2)]">
            {t(PROVIDER_KIND_LABELS[provider.kind])}
          </span>
          {provider.shared && (
            <span className="rounded bg-indigo-500/15 px-1.5 py-0.5 text-[10px] text-indigo-600 dark:text-indigo-300">
              {t('settings.providerShared')}
            </span>
          )}
        </div>
        <span className="text-xs text-[var(--muted-2)]">
          {provider.credential_configured
            ? t('settings.providerKeyConfigured')
            : t('settings.providerKeyMissing')}
        </span>
      </div>

      {canManage ? (
        <>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block text-xs text-[var(--text-2)]">
              {t('settings.providerName')}
              <input
                value={name}
                onChange={(event) => {
                  setName(event.target.value)
                  setSaved(false)
                }}
                className={inputClass}
                maxLength={100}
              />
            </label>
            <label className="block text-xs text-[var(--text-2)]">
              {t('settings.providerApiKey')}
              <input
                type="password"
                value={apiKey}
                onChange={(event) => {
                  setApiKey(event.target.value)
                  setSaved(false)
                }}
                className={inputClass}
                autoComplete="new-password"
                placeholder={t('settings.providerKeyPlaceholder')}
              />
            </label>
          </div>
          <p className="mt-1 text-xs text-[var(--muted-2)]">{t('settings.providerKeyHint')}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={save}
              disabled={!name.trim() || busy !== null}
              className="rounded-md bg-[var(--hover)] px-3 py-1.5 text-xs text-[var(--fg-2)] transition hover:bg-[var(--hover-strong)] disabled:opacity-50"
            >
              {busy === 'save' ? t('settings.saving') : t('settings.save')}
            </button>
            <button
              type="button"
              onClick={testConnection}
              disabled={!provider.credential_configured || busy !== null}
              className="rounded-md border border-[var(--border-strong)] px-3 py-1.5 text-xs text-[var(--fg-2)] transition hover:bg-[var(--hover)] disabled:opacity-50"
            >
              {busy === 'test' ? t('settings.providerTesting') : t('settings.providerTest')}
            </button>
            <button
              type="button"
              onClick={remove}
              disabled={busy !== null}
              className="rounded-md px-3 py-1.5 text-xs text-[var(--danger)] transition hover:bg-[var(--hover)] disabled:opacity-50"
            >
              {busy === 'delete' ? t('settings.providerDeleting') : t('settings.providerDelete')}
            </button>
            {saved && (
              <span className="text-xs text-emerald-600 dark:text-emerald-400">
                {t('settings.saved')}
              </span>
            )}
          </div>
        </>
      ) : (
        <p className="mt-2 text-xs text-[var(--muted-2)]">
          {t('settings.providerSharedReadOnly')}
        </p>
      )}

      {error && <p className="mt-2 text-sm text-[var(--danger)]">{error}</p>}
      {models && (
        <div className="mt-3 rounded-md border border-[var(--border)] bg-[var(--bg)] p-3">
          <p className="text-xs font-medium text-[var(--fg-2)]">
            {t('settings.providerModelsFound', { count: models.length })}
          </p>
          {models.length > 0 && (
            <ul className="mt-2 grid max-h-36 gap-1 overflow-y-auto sm:grid-cols-2">
              {models.map((model) => (
                <li key={model.id} className="truncate text-xs text-[var(--muted-2)]" title={model.id}>
                  {model.display_name}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  )
}

export function ProviderSettings() {
  const { t } = useTranslation()
  const [providers, setProviders] = useState<AIProvider[] | null>(null)
  const [canManageShared, setCanManageShared] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [name, setName] = useState('')
  const [kind, setKind] = useState<AIProviderKind>('openai')
  const [apiKey, setApiKey] = useState('')
  const [shared, setShared] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')

  useEffect(() => {
    let active = true
    fetchAIProviders()
      .then((result) => {
        if (!active) return
        setProviders(result.providers)
        setCanManageShared(result.can_manage_shared)
      })
      .catch(() => {
        if (active) setLoadError(true)
      })
    return () => {
      active = false
    }
  }, [])

  async function addProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!name.trim() || !apiKey.trim()) return
    setCreating(true)
    setCreateError('')
    try {
      const created = await createAIProvider(
        { name: name.trim(), kind, api_key: apiKey.trim() },
        shared,
      )
      setProviders((current) => [...(current ?? []), created])
      setName('')
      setApiKey('')
    } catch (reason) {
      setCreateError(
        reason instanceof Error ? reason.message : t('settings.providerActionFailed'),
      )
    } finally {
      setCreating(false)
    }
  }

  return (
    <section className="mb-6">
      <h2 className="mb-1 text-sm font-semibold text-[var(--fg-strong)]">
        {t('settings.providers')}
      </h2>
      <p className="mb-4 text-sm text-[var(--text-2)]">{t('settings.providersDescription')}</p>

      <form
        onSubmit={addProvider}
        className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block text-xs text-[var(--text-2)]">
            {t('settings.providerName')}
            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={inputClass}
              maxLength={100}
            />
          </label>
          <label className="block text-xs text-[var(--text-2)]">
            {t('settings.providerKind')}
            <select
              value={kind}
              onChange={(event) => {
                const selected = PROVIDER_KINDS.find((item) => item === event.target.value)
                if (selected) setKind(selected)
              }}
              className={inputClass}
            >
              {PROVIDER_KINDS.map((providerKind) => (
                <option key={providerKind} value={providerKind}>
                  {t(PROVIDER_KIND_LABELS[providerKind])}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs text-[var(--text-2)]">
            {t('settings.providerApiKey')}
            <input
              required
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              className={inputClass}
              autoComplete="new-password"
            />
          </label>
        </div>
        {canManageShared && (
          <label className="mt-3 flex w-fit items-center gap-2 text-xs text-[var(--text-2)]">
            <input
              type="checkbox"
              checked={shared}
              onChange={(event) => setShared(event.target.checked)}
            />
            {t('settings.providerShared')}
          </label>
        )}
        <div className="mt-3 flex items-center gap-3">
          <button
            type="submit"
            disabled={creating || !name.trim() || !apiKey.trim()}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {creating ? t('settings.providerAdding') : t('settings.providerAdd')}
          </button>
          {createError && <span className="text-xs text-[var(--danger)]">{createError}</span>}
        </div>
        <p className="mt-2 text-xs text-[var(--muted-2)]">{t('settings.providerKeyHint')}</p>
      </form>

      {loadError && (
        <p className="mb-3 text-sm text-[var(--danger)]">{t('settings.providerLoadFailed')}</p>
      )}
      {providers === null && !loadError && (
        <p className="text-sm text-[var(--muted-2)]">{t('common.loading')}</p>
      )}
      {providers?.length === 0 && (
        <p className="text-sm text-[var(--muted-2)]">{t('settings.providerEmpty')}</p>
      )}
      {providers && providers.length > 0 && (
        <div className="space-y-3">
          {providers.map((provider) => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              canManage={!provider.shared || canManageShared}
              onUpdate={(updated) =>
                setProviders((current) =>
                  current?.map((item) => (item.id === updated.id ? updated : item)) ?? null,
                )
              }
              onDelete={(providerId) =>
                setProviders((current) => current?.filter((item) => item.id !== providerId) ?? null)
              }
            />
          ))}
        </div>
      )}
    </section>
  )
}
