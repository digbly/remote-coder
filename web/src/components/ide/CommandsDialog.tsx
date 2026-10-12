import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  newCommandId,
  type CommandDefinition,
  type CommandScope,
} from '../../lib/workspaceStore'
import { CloseIcon, CommandIcon, PencilIcon, TrashIcon } from './icons'

const inputClass =
  'w-full rounded-lg border border-[var(--hover-strong)] bg-[var(--input)] px-3 py-2 text-sm text-[var(--fg)] outline-none transition placeholder:text-[var(--muted-3)] focus:border-indigo-500'
const labelClass = 'mb-1 block text-[12px] font-medium text-[var(--fg-3)]'

interface CommandsDialogProps {
  projectCommands: CommandDefinition[]
  globalCommands: CommandDefinition[]
  projectName: string | null
  onSave: (scope: CommandScope, command: CommandDefinition) => void
  onDelete: (scope: CommandScope, commandId: string) => void
  onClose: () => void
}

export function CommandsDialog({
  projectCommands,
  globalCommands,
  projectName,
  onSave,
  onDelete,
  onClose,
}: CommandsDialogProps) {
  const { t } = useTranslation()
  const [scope, setScope] = useState<CommandScope>(projectName ? 'project' : 'global')
  const [label, setLabel] = useState('')
  const [lines, setLines] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const commands = scope === 'project' ? projectCommands : globalCommands

  function resetForm() {
    setLabel('')
    setLines('')
    setEditingId(null)
    setError(null)
  }

  function switchScope(next: CommandScope) {
    if (next === 'project' && projectName == null) return
    setScope(next)
    resetForm()
  }

  function beginEdit(command: CommandDefinition) {
    setEditingId(command.id)
    setLabel(command.label)
    setLines(command.commands.join('\n'))
    setError(null)
  }

  function handleDelete(commandId: string) {
    onDelete(scope, commandId)
    if (editingId === commandId) resetForm()
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedLabel = label.trim()
    const parsedLines = lines
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
    if (!trimmedLabel) {
      setError(t('ide.commandsErrorLabel'))
      return
    }
    if (parsedLines.length === 0) {
      setError(t('ide.commandsErrorLines'))
      return
    }
    onSave(scope, {
      id: editingId ?? newCommandId(),
      label: trimmedLabel,
      commands: parsedLines,
    })
    resetForm()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/60 sm:items-center sm:justify-center sm:p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="commands-dialog-title"
        className="flex h-full w-full flex-col overflow-hidden border-[var(--border)] bg-[var(--surface)] pt-[var(--safe-top)] sm:h-auto sm:max-h-[90vh] sm:max-w-lg sm:rounded-xl sm:shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <h2
            id="commands-dialog-title"
            className="flex items-center gap-2 text-sm font-semibold text-[var(--fg-strong)]"
          >
            <CommandIcon width={15} height={15} />
            {t('ide.commandsDialogTitle')}
          </h2>
          <button
            type="button"
            aria-label={t('ide.commandsCancel')}
            onClick={onClose}
            className="rounded-md p-1 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>

        <div className="flex shrink-0 gap-1 px-4 pt-3">
          {(['project', 'global'] as const).map((value) => {
            const disabled = value === 'project' && projectName == null
            return (
              <button
                key={value}
                type="button"
                disabled={disabled}
                onClick={() => switchScope(value)}
                className={`rounded-md px-3 py-1.5 text-[13px] transition disabled:cursor-not-allowed disabled:opacity-40 ${
                  scope === value
                    ? 'bg-[var(--hover)] text-[var(--fg-strong)]'
                    : 'text-[var(--text-2)] hover:bg-[var(--hover-subtle)] hover:text-[var(--fg-strong)]'
                }`}
              >
                {value === 'project'
                  ? projectName ?? t('ide.commandsScopeProject')
                  : t('ide.commandsScopeGlobal')}
              </button>
            )
          })}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <p className="mb-3 text-xs text-[var(--muted-2)]">
            {scope === 'project'
              ? t('ide.commandsProjectScopeHint')
              : t('ide.commandsGlobalScopeHint')}
          </p>

          {commands.length === 0 ? (
            <p className="mb-4 text-sm text-[var(--muted-2)]">{t('ide.commandsEmpty')}</p>
          ) : (
            <ul className="mb-4 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
              {commands.map((command) => (
                <li key={command.id} className="flex items-start gap-2 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-[var(--fg-strong)]">{command.label}</p>
                    <p className="truncate font-mono text-[11px] text-[var(--muted-2)]">
                      {command.commands.join(' ; ')}
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label={t('ide.commandsEdit')}
                    title={t('ide.commandsEdit')}
                    onClick={() => beginEdit(command)}
                    className="shrink-0 rounded p-1 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
                  >
                    <PencilIcon width={13} height={13} />
                  </button>
                  <button
                    type="button"
                    aria-label={t('ide.commandsDelete')}
                    title={t('ide.commandsDelete')}
                    onClick={() => handleDelete(command.id)}
                    className="shrink-0 rounded p-1 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--danger)]"
                  >
                    <TrashIcon width={13} height={13} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            {error && (
              <p
                role="alert"
                className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-[var(--danger)] ring-1 ring-red-500/30"
              >
                {error}
              </p>
            )}
            <div>
              <label htmlFor="command-label" className={labelClass}>
                {t('ide.commandsLabelLabel')}
              </label>
              <input
                id="command-label"
                type="text"
                autoFocus
                value={label}
                onChange={(event) => {
                  setLabel(event.target.value)
                  setError(null)
                }}
                placeholder={t('ide.commandsLabelPlaceholder')}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="command-lines" className={labelClass}>
                {t('ide.commandsLinesLabel')}
              </label>
              <textarea
                id="command-lines"
                rows={4}
                spellCheck={false}
                value={lines}
                onChange={(event) => {
                  setLines(event.target.value)
                  setError(null)
                }}
                placeholder={t('ide.commandsLinesPlaceholder')}
                className={`${inputClass} resize-y font-mono`}
              />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-lg px-3 py-2 text-sm text-[var(--fg-3)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)]"
                >
                  {t('ide.commandsCancel')}
                </button>
              )}
              <button
                type="submit"
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
              >
                {editingId ? t('ide.commandsSave') : t('ide.commandsAdd')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
