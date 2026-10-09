import { useCallback, useEffect, useRef, useState } from 'react'

interface AsyncData<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/**
 * Load data on mount and whenever `deps` change or `reload` is called.
 *
 * Results from a superseded request are discarded, so rapid project switches
 * cannot let a stale response overwrite the current one.
 */
export function useAsyncData<T>(
  load: () => Promise<T>,
  fallbackError: string,
  deps: readonly unknown[],
): AsyncData<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)
  const loadRef = useRef(load)

  useEffect(() => {
    loadRef.current = load
  })

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  useEffect(() => {
    let active = true
    loadRef
      .current()
      .then((next) => {
        if (!active) return
        setData(next)
        setError(null)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : fallbackError)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fallbackError, reloadToken, ...deps])

  return { data, error, loading, reload }
}
