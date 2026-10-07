import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { browseDirectories, type DirectoryListing } from '../../lib/api'
import { ArrowUpIcon, ChevronRightIcon, CloseIcon, FolderIcon } from './icons'

interface FolderBrowserDialogProps {
  initialPath?: string
  onSelect: (path: string) => void
  onClose: () => void
}

export function FolderBrowserDialog({
  initialPath,
  onSelect,
  onClose,
}: FolderBrowserDialogProps) {
  const { t } = useTranslation()
  const [listing, setListing] = useState<DirectoryListing | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const result = await browseDirectories(initialPath)
        if (active) setListing(result)
      } catch (err) {
        if (initialPath) {
          try {
            const fallback = await browseDirectories()
            if (active) setListing(fallback)
            return
          } catch (fallbackErr) {
            if (active) setError(fallbackErr)
            return
          }
        }
        if (active) setError(err)
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [initialPath])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  async function navigate(path: string) {
    setLoading(true)
    setError(null)
    try {
      setListing(await browseDirectories(path))
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
      onClick={(event) => {
        event.stopPropagation()
        onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="folder-browser-title"
        className="flex w-full max-w-lg flex-col rounded-xl border border-[#2c2e33] bg-[#1b1c1f] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[#2c2e33] px-4 py-3">
          <h2 id="folder-browser-title" className="text-sm font-semibold text-white">
            {t('ide.folderBrowser.title')}
          </h2>
          <button
            type="button"
            aria-label={t('ide.folderBrowser.cancel')}
            onClick={onClose}
            className="rounded-md p-1 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white"
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>

        <div className="flex items-center gap-2 border-b border-[#2c2e33] px-4 py-2">
          <button
            type="button"
            aria-label={t('ide.folderBrowser.up')}
            title={t('ide.folderBrowser.up')}
            disabled={!listing?.parent || loading}
            onClick={() => {
              if (listing?.parent) void navigate(listing.parent)
            }}
            className="rounded-md p-1.5 text-[#8b9099] transition hover:bg-[#2a2c30] hover:text-white disabled:opacity-40 disabled:hover:bg-transparent"
          >
            <ArrowUpIcon width={15} height={15} />
          </button>
          <span className="truncate font-mono text-[12px] text-[#9aa0a8]" title={listing?.path}>
            {listing?.path ?? ''}
          </span>
        </div>

        <div className="h-72 overflow-y-auto px-2 py-2">
          {error != null && (
            <p role="alert" className="px-2 py-1.5 text-[13px] text-[#f0a9b0]">
              {error instanceof Error ? error.message : t('apiErrors.unknown')}
            </p>
          )}
          {loading && !error && (
            <p className="px-2 py-1.5 text-[13px] text-[#7d828b]">
              {t('ide.folderBrowser.loading')}
            </p>
          )}
          {!loading && !error && listing?.directories.length === 0 && (
            <p className="px-2 py-1.5 text-[13px] text-[#7d828b]">
              {t('ide.folderBrowser.empty')}
            </p>
          )}
          {!error &&
            listing?.directories.map((entry) => (
              <button
                key={entry.path}
                type="button"
                disabled={loading}
                onClick={() => void navigate(entry.path)}
                title={entry.path}
                className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13px] text-[#c2c6cc] transition hover:bg-[#24262a] hover:text-white disabled:opacity-60"
              >
                <FolderIcon width={15} height={15} className="shrink-0 text-amber-400" />
                <span className="truncate">{entry.name}</span>
                <ChevronRightIcon
                  width={14}
                  height={14}
                  className="ml-auto shrink-0 text-[#6b7078]"
                />
              </button>
            ))}
        </div>

        <div className="flex justify-end gap-2 border-t border-[#2c2e33] px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm text-[#c2c6cc] transition hover:bg-[#2a2c30] hover:text-white"
          >
            {t('ide.folderBrowser.cancel')}
          </button>
          <button
            type="button"
            disabled={!listing || loading}
            onClick={() => {
              if (listing) onSelect(listing.path)
            }}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t('ide.folderBrowser.select')}
          </button>
        </div>
      </div>
    </div>
  )
}
