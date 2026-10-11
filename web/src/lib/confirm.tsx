import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmContext, type ConfirmFn, type ConfirmOptions } from './confirmContext'

function ConfirmDialog({
  options,
  onResolve,
}: {
  options: ConfirmOptions
  onResolve: (value: boolean) => void
}) {
  const { t } = useTranslation()
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    confirmRef.current?.focus()
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onResolve(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onResolve])

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 px-4 pb-[var(--safe-bottom)] pt-4 sm:items-center"
      onMouseDown={() => onResolve(false)}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label={options.title ?? options.message}
        onMouseDown={(event) => event.stopPropagation()}
        className="w-full max-w-sm rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 shadow-2xl shadow-black/50"
      >
        {options.title && (
          <h2 className="text-sm font-semibold text-[var(--fg-strong)]">{options.title}</h2>
        )}
        <p className="mt-1 text-sm text-[var(--fg-2)]">{options.message}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => onResolve(false)}
            className="rounded-md border border-[var(--border-strong)] px-4 py-2 text-sm text-[var(--fg-2)] transition hover:bg-[var(--hover)]"
          >
            {options.cancelLabel ?? t('common.cancel')}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={() => onResolve(true)}
            className={`rounded-md px-4 py-2 text-sm font-medium text-white transition ${
              options.destructive
                ? 'bg-[var(--danger)] hover:opacity-90'
                : 'bg-indigo-600 hover:bg-indigo-500'
            }`}
          >
            {options.confirmLabel ?? t('common.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const requestRef = useRef<{ options: ConfirmOptions; resolve: (value: boolean) => void } | null>(
    null,
  )
  const [request, setRequest] = useState<ConfirmOptions | null>(null)

  const confirm = useCallback<ConfirmFn>(
    (options) =>
      new Promise<boolean>((resolve) => {
        requestRef.current = { options, resolve }
        setRequest(options)
      }),
    [],
  )

  const settle = useCallback((value: boolean) => {
    requestRef.current?.resolve(value)
    requestRef.current = null
    setRequest(null)
  }, [])

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request && <ConfirmDialog options={request} onResolve={settle} />}
    </ConfirmContext.Provider>
  )
}
