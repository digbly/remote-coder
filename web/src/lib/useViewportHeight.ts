import { useEffect, useState } from 'react'

/**
 * Live height of the visual viewport. On mobile this shrinks when the soft
 * keyboard opens, so sizing the shell to it keeps the composer and terminal
 * toolbar above the keyboard instead of hidden behind it. Returns `null` when
 * `visualViewport` is unavailable, letting the caller fall back to CSS units.
 */
export function useViewportHeight(): number | null {
  const [height, setHeight] = useState<number | null>(() =>
    typeof window !== 'undefined' && window.visualViewport ? window.visualViewport.height : null,
  )

  useEffect(() => {
    const viewport = window.visualViewport
    if (!viewport) return
    const update = () => setHeight((prev) => (prev === viewport.height ? prev : viewport.height))
    update()
    viewport.addEventListener('resize', update)
    viewport.addEventListener('scroll', update)
    return () => {
      viewport.removeEventListener('resize', update)
      viewport.removeEventListener('scroll', update)
    }
  }, [])

  return height
}
