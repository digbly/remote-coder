import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react'

const KEYBOARD_STEP = 16

interface ResizeHandleProps {
  side: 'left' | 'right'
  width: number
  min: number
  max: number
  onResize: (width: number) => void
  label: string
}

export function ResizeHandle({ side, width, min, max, onResize, label }: ResizeHandleProps) {
  const clamp = (value: number) => Math.min(max, Math.max(min, value))

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    event.preventDefault()
    const handle = event.currentTarget
    const startX = event.clientX
    const startWidth = width
    handle.setPointerCapture(event.pointerId)

    function handleMove(moveEvent: PointerEvent) {
      const delta = moveEvent.clientX - startX
      onResize(clamp(side === 'left' ? startWidth + delta : startWidth - delta))
    }

    function stop() {
      handle.removeEventListener('pointermove', handleMove)
      handle.removeEventListener('pointerup', stop)
      handle.removeEventListener('pointercancel', stop)
    }

    handle.addEventListener('pointermove', handleMove)
    handle.addEventListener('pointerup', stop)
    handle.addEventListener('pointercancel', stop)
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const direction = side === 'left' ? 1 : -1
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      onResize(clamp(width + direction * KEYBOARD_STEP))
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      onResize(clamp(width - direction * KEYBOARD_STEP))
    }
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={Math.round(width)}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
      className="relative z-10 w-px shrink-0 cursor-col-resize touch-none bg-[var(--border)] transition-colors hover:bg-[var(--accent)] focus-visible:bg-[var(--accent)] focus-visible:outline-none"
    >
      <span className="absolute inset-y-0 -left-1 -right-1" />
    </div>
  )
}
