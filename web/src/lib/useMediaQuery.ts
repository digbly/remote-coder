import { useEffect, useState } from 'react'

/** Breakpoint at which the workspace switches to the single-column mobile shell. */
export const MOBILE_QUERY = '(max-width: 767px)'

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  )

  useEffect(() => {
    const media = window.matchMedia(query)
    const handleChange = () => setMatches(media.matches)
    handleChange()
    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [query])

  return matches
}

/** True on viewports narrow enough to use the mobile shell. */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_QUERY)
}
