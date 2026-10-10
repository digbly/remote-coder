import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  applyResolvedTheme,
  DARK_QUERY,
  getStoredTheme,
  resolveTheme,
  THEME_STORAGE_KEY,
  ThemeContext,
  type ResolvedTheme,
  type ThemeContextValue,
  type ThemeMode,
} from './themeContext'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(getStoredTheme)
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme(getStoredTheme()))

  useEffect(() => {
    applyResolvedTheme(resolved)
  }, [resolved])

  useEffect(() => {
    if (mode !== 'system') return
    const query = window.matchMedia(DARK_QUERY)
    const onChange = () => setResolved(resolveTheme('system'))
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [mode])

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next)
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      /* storage unavailable */
    }
    setResolved(resolveTheme(next))
  }, [])

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, resolved, setMode }),
    [mode, resolved, setMode],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
