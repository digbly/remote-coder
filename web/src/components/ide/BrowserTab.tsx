import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import {
  browserStreamUrl,
  controlBrowser,
  fetchBrowserSelection,
  insertBrowserText,
  navigateBrowser,
  setBrowserViewport,
} from '../../lib/api'
import { ArrowLeftIcon, ArrowRightIcon, GlobeIcon, MaximizeIcon, MinimizeIcon, RefreshIcon } from './icons'

interface FrameMessage {
  data: string
  metadata?: { deviceWidth?: number; deviceHeight?: number }
}

type ConnectionState = 'connecting' | 'open' | 'closed'

const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 15000

function normalizeUrl(raw: string): string {
  const value = raw.trim()
  if (value === '') return ''
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(value)) return value
  if (value.startsWith('//')) return `https:${value}`
  return `http://${value}`
}

function modifierBits(event: {
  altKey: boolean
  ctrlKey: boolean
  metaKey: boolean
  shiftKey: boolean
}): number {
  return (
    (event.altKey ? 1 : 0) |
    (event.ctrlKey ? 2 : 0) |
    (event.metaKey ? 4 : 0) |
    (event.shiftKey ? 8 : 0)
  )
}

function mouseButton(button: number): string {
  if (button === 2) return 'right'
  if (button === 1) return 'middle'
  return 'left'
}

export function BrowserTab({
  projectId,
  sessionId,
}: {
  projectId: number
  sessionId: string
}) {
  const { t } = useTranslation()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const pendingRef = useRef<FrameMessage | null>(null)
  const loadingRef = useRef(false)
  const loadNextRef = useRef<() => void>(() => {})
  const fitCanvasRef = useRef<() => void>(() => {})
  const fatalRef = useRef(false)
  const moveFrameRef = useRef<number | null>(null)
  const movePointRef = useRef<{ x: number; y: number } | null>(null)

  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const [address, setAddress] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [reconnectNonce, setReconnectNonce] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [caret, setCaret] = useState<{ left: number; top: number }>({ left: 0, top: 0 })

  const send = useCallback((payload: unknown) => {
    const socket = socketRef.current
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload))
  }, [])

  const drawFrame = useCallback((image: HTMLImageElement, frame: FrameMessage) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const width = frame.metadata?.deviceWidth ?? image.naturalWidth
    const height = frame.metadata?.deviceHeight ?? image.naturalHeight
    if (width > 0 && height > 0 && (canvas.width !== width || canvas.height !== height)) {
      canvas.width = width
      canvas.height = height
    }
    const context = canvas.getContext('2d')
    if (!context) return
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    fitCanvasRef.current()
  }, [])

  const loadNext = useCallback(() => {
    const frame = pendingRef.current
    if (!frame) return
    pendingRef.current = null
    loadingRef.current = true
    const image = imageRef.current ?? new Image()
    imageRef.current = image
    image.onload = () => {
      drawFrame(image, frame)
      loadingRef.current = false
      if (pendingRef.current) loadNextRef.current()
    }
    image.onerror = () => {
      loadingRef.current = false
      if (pendingRef.current) loadNextRef.current()
    }
    image.src = `data:image/jpeg;base64,${frame.data}`
  }, [drawFrame])

  useEffect(() => {
    loadNextRef.current = loadNext
  }, [loadNext])

  const fitCanvas = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container || canvas.width === 0 || canvas.height === 0) return
    // Size the element to the contained image so the element box always equals
    // the drawn frame; pointer mapping then needs no letterbox math.
    const scale = Math.min(
      container.clientWidth / canvas.width,
      container.clientHeight / canvas.height,
    )
    canvas.style.width = `${Math.round(canvas.width * scale)}px`
    canvas.style.height = `${Math.round(canvas.height * scale)}px`
  }, [])

  useEffect(() => {
    fitCanvasRef.current = fitCanvas
  }, [fitCanvas])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    // Resize the remote viewport to match the pane so the page reflows to fill
    // it: the canvas then renders 1:1 (no letterbox) and pointer input maps
    // exactly. Debounced because each change is a remote command.
    let timer: number | null = null
    let lastWidth = 0
    let lastHeight = 0
    const observer = new ResizeObserver(() => {
      fitCanvasRef.current()
      const width = Math.round(container.clientWidth)
      const height = Math.round(container.clientHeight)
      if (width < 200 || height < 200) return
      if (width === lastWidth && height === lastHeight) return
      if (timer !== null) window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        lastWidth = width
        lastHeight = height
        void setBrowserViewport(projectId, sessionId, width, height).catch(() => undefined)
      }, 300)
    })
    observer.observe(container)
    return () => {
      observer.disconnect()
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [projectId, sessionId])

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let attempts = 0

    function handleMessage(raw: string) {
      let message: unknown
      try {
        message = JSON.parse(raw)
      } catch {
        return
      }
      if (typeof message !== 'object' || message === null) return
      const data = message as Record<string, unknown>
      if (data.type === 'frame' && typeof data.data === 'string') {
        setConnection('open')
        setError(null)
        pendingRef.current = {
          data: data.data,
          metadata: data.metadata as FrameMessage['metadata'],
        }
        if (!loadingRef.current) loadNextRef.current()
      } else if (data.type === 'status') {
        // The stream is up even before the first frame (blank page, no change),
        // so treat status as connected instead of stalling on "connecting".
        setConnection('open')
      } else if (data.type === 'url' && typeof data.url === 'string') {
        setAddress(data.url)
      } else if (data.type === 'error') {
        fatalRef.current = true
        setError(
          typeof data.message === 'string' && data.message ? data.message : t('apiErrors.unknown'),
        )
        setConnection('closed')
      }
    }

    function open() {
      if (cancelled) return
      setConnection('connecting')
      const ws = new WebSocket(browserStreamUrl(projectId, sessionId))
      socket = ws
      socketRef.current = ws

      ws.onopen = () => {
        attempts = 0
        setConnection('connecting')
        setError(null)
      }
      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          handleMessage(event.data)
          return
        }
        // The stream protocol is JSON text; decode unexpected binary frames so
        // a Blob never silently stalls the render loop.
        const blob = event.data as Blob
        void blob
          .text()
          .then(handleMessage)
          .catch(() => undefined)
      }
      ws.onclose = (event) => {
        if (cancelled) return
        if (socketRef.current === ws) socketRef.current = null
        if (
          fatalRef.current ||
          event.code === 4401 ||
          event.code === 4403 ||
          event.code === 4404
        ) {
          setConnection('closed')
          return
        }
        setConnection('connecting')
        attempts += 1
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** (attempts - 1), RECONNECT_MAX_MS)
        reconnectTimer = window.setTimeout(open, delay)
      }
    }

    open()
    return () => {
      cancelled = true
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      if (moveFrameRef.current !== null) window.cancelAnimationFrame(moveFrameRef.current)
      if (socket && socketRef.current === socket) socketRef.current = null
      socket?.close()
    }
  }, [projectId, sessionId, reconnectNonce, t])

  useEffect(() => {
    function onChange() {
      setIsFullscreen(document.fullscreenElement === containerRef.current)
      fitCanvasRef.current()
    }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  function toggleFullscreen() {
    if (document.fullscreenElement) {
      void document.exitFullscreen()
    } else {
      void containerRef.current?.requestFullscreen()
    }
  }

  function targetPoint(event: { clientX: number; clientY: number }) {
    const canvas = canvasRef.current
    if (!canvas || canvas.width === 0 || canvas.height === 0) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return { x: 0, y: 0 }
    return {
      x: Math.round(((event.clientX - rect.left) / rect.width) * canvas.width),
      y: Math.round(((event.clientY - rect.top) / rect.height) * canvas.height),
    }
  }

  function onPointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const { x, y } = targetPoint(event)
    // Coalesce moves to one event per animation frame so a fast pointer does
    // not flood the stream with hundreds of messages per second.
    movePointRef.current = { x, y }
    if (moveFrameRef.current !== null) return
    moveFrameRef.current = window.requestAnimationFrame(() => {
      moveFrameRef.current = null
      const point = movePointRef.current
      if (point) send({ type: 'input_mouse', eventType: 'mouseMoved', x: point.x, y: point.y })
    })
  }

  function onPointerDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    event.preventDefault()
    const { x, y } = targetPoint(event)
    const canvas = canvasRef.current
    const rect = canvas?.getBoundingClientRect()
    const containerRect = containerRef.current?.getBoundingClientRect()
    // Park the hidden input at the click point so IME candidates appear there,
    // then focus it: it is the sink for typed/pasted/composed text.
    if (rect && containerRect && canvas) {
      setCaret({
        left: rect.left - containerRect.left + (x / canvas.width) * rect.width,
        top: rect.top - containerRect.top + (y / canvas.height) * rect.height,
      })
    }
    inputRef.current?.focus()
    const button = mouseButton(event.button)
    // Move first so the server sees the cursor position before the press.
    send({ type: 'input_mouse', eventType: 'mouseMoved', x, y })
    send({ type: 'input_mouse', eventType: 'mousePressed', x, y, button, clickCount: 1 })
  }

  function onPointerUp(event: ReactPointerEvent<HTMLCanvasElement>) {
    const { x, y } = targetPoint(event)
    send({
      type: 'input_mouse',
      eventType: 'mouseReleased',
      x,
      y,
      button: mouseButton(event.button),
    })
  }

  function onWheel(event: ReactWheelEvent<HTMLCanvasElement>) {
    if (event.ctrlKey || event.metaKey) {
      // Ctrl/Cmd + wheel zooms, like a real browser.
      event.preventDefault()
      const zoomIn = event.deltaY < 0
      const key = zoomIn ? '+' : '-'
      const code = zoomIn ? 'Equal' : 'Minus'
      const virtualKeyCode = zoomIn ? 187 : 189
      for (const eventType of ['keyDown', 'keyUp'] as const) {
        send({
          type: 'input_keyboard',
          eventType,
          key,
          code,
          modifiers: 2,
          windowsVirtualKeyCode: virtualKeyCode,
          nativeVirtualKeyCode: virtualKeyCode,
        })
      }
      return
    }
    const { x, y } = targetPoint(event)
    send({
      type: 'input_mouse',
      eventType: 'mouseWheel',
      x,
      y,
      deltaX: event.deltaX,
      deltaY: event.deltaY,
    })
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    const native = event.nativeEvent
    if (native.isComposing || event.keyCode === 229) return
    if (event.ctrlKey && event.altKey) {
      event.currentTarget.blur()
      return
    }
    const accel = event.ctrlKey || event.metaKey
    if (accel && !event.altKey && (event.key === 'v' || event.key === 'V')) {
      // Let the browser perform the paste into the hidden input; onInput then
      // forwards the pasted text. This avoids clipboard read permission.
      return
    }
    if (event.key.length === 1 && !accel && !event.altKey) {
      // Printable text flows through the hidden input's onInput so IME and
      // typematic input share one path.
      return
    }
    event.preventDefault()
    if (accel && !event.altKey && 'cCxX'.includes(event.key)) {
      // Read the selection before the remote acts, so a cut still reaches the
      // user's clipboard; then forward the shortcut for the remote's own copy.
      void copyOrCut(event.key === 'x' || event.key === 'X')
      return
    }
    // Non-text keys (Backspace, Delete, arrows, Enter, ...) need the virtual
    // key code; without it the remote browser ignores them. Enter also needs
    // its carriage-return text so textareas/forms react.
    const virtualKeyCode = event.keyCode
    send({
      type: 'input_keyboard',
      eventType: 'keyDown',
      key: event.key,
      code: event.code,
      modifiers: modifierBits(event),
      windowsVirtualKeyCode: virtualKeyCode,
      nativeVirtualKeyCode: virtualKeyCode,
      ...(event.key === 'Enter' ? { text: '\r' } : {}),
    })
  }

  function onInput(event: React.FormEvent<HTMLTextAreaElement>) {
    const element = event.currentTarget
    const native = event.nativeEvent as InputEvent
    if (native.isComposing) return
    const value = element.value
    if (value === '') return
    element.value = ''
    if (value.length === 1) {
      send({ type: 'input_keyboard', eventType: 'char', text: value })
    } else {
      void insertBrowserText(projectId, sessionId, value).catch(() => undefined)
    }
  }

  function onCompositionEnd(event: React.CompositionEvent<HTMLTextAreaElement>) {
    // Guarantees an IME commit is forwarded even if the trailing `input` event
    // never arrives; whichever runs first clears the value so the other no-ops.
    const element = event.currentTarget
    const value = element.value
    if (value === '') return
    element.value = ''
    void insertBrowserText(projectId, sessionId, value).catch(() => undefined)
  }

  function onKeyUp(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.nativeEvent.isComposing) return
    if (event.key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) return
    const virtualKeyCode = event.keyCode
    send({
      type: 'input_keyboard',
      eventType: 'keyUp',
      key: event.key,
      code: event.code,
      modifiers: modifierBits(event),
      windowsVirtualKeyCode: virtualKeyCode,
      nativeVirtualKeyCode: virtualKeyCode,
    })
  }

  async function submitAddress(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = normalizeUrl(address)
    if (next === '') return
    try {
      await navigateBrowser(projectId, sessionId, next)
      inputRef.current?.focus()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiErrors.unknown'))
    }
  }

  async function control(action: 'back' | 'forward' | 'reload') {
    try {
      await controlBrowser(projectId, sessionId, action)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiErrors.unknown'))
    }
  }

  async function copyOrCut(cut: boolean) {
    try {
      const text = await fetchBrowserSelection(projectId, sessionId)
      if (text) await navigator.clipboard.writeText(text)
    } catch {
      /* clipboard access can be denied; the remote still copies below */
    }
    const virtualKeyCode = cut ? 88 : 67
    for (const eventType of ['keyDown', 'keyUp'] as const) {
      send({
        type: 'input_keyboard',
        eventType,
        key: cut ? 'x' : 'c',
        code: cut ? 'KeyX' : 'KeyC',
        modifiers: 2,
        windowsVirtualKeyCode: virtualKeyCode,
        nativeVirtualKeyCode: virtualKeyCode,
      })
    }
  }

  const toolbarButton =
    'shrink-0 rounded-md p-1.5 text-[var(--muted)] transition hover:bg-[var(--hover)] hover:text-[var(--fg-strong)] disabled:opacity-40 disabled:hover:bg-transparent'

  return (
    <div className="flex h-full w-full flex-col bg-[var(--bg)]">
      <form
        onSubmit={submitAddress}
        className="flex items-center gap-1.5 border-b border-[var(--border)] bg-[var(--surface)] px-2 py-1.5"
      >
        <button
          type="button"
          aria-label={t('ide.browserBack')}
          title={t('ide.browserBack')}
          onClick={() => void control('back')}
          className={toolbarButton}
        >
          <ArrowLeftIcon width={14} height={14} />
        </button>
        <button
          type="button"
          aria-label={t('ide.browserForward')}
          title={t('ide.browserForward')}
          onClick={() => void control('forward')}
          className={toolbarButton}
        >
          <ArrowRightIcon width={14} height={14} />
        </button>
        <button
          type="button"
          aria-label={t('ide.browserReload')}
          title={t('ide.browserReload')}
          onClick={() => void control('reload')}
          className={toolbarButton}
        >
          <RefreshIcon width={14} height={14} />
        </button>
        <button
          type="button"
          aria-label={isFullscreen ? t('ide.browserExitFullscreen') : t('ide.browserFullscreen')}
          title={isFullscreen ? t('ide.browserExitFullscreen') : t('ide.browserFullscreen')}
          onClick={toggleFullscreen}
          className={toolbarButton}
        >
          {isFullscreen ? <MinimizeIcon width={14} height={14} /> : <MaximizeIcon width={14} height={14} />}
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--input)] px-2.5 py-1 focus-within:border-indigo-500">
          <GlobeIcon width={13} height={13} className="shrink-0 text-[var(--muted-2)]" />
          <input
            type="text"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            placeholder={t('ide.browserPlaceholder')}
            aria-label={t('ide.browserAddress')}
            spellCheck={false}
            className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-[var(--fg-2)] outline-none placeholder:text-[var(--muted-3)]"
          />
        </div>
        <button
          type="submit"
          disabled={address.trim() === ''}
          className="shrink-0 rounded-md bg-[var(--hover)] px-2.5 py-1 text-[12px] text-[var(--fg-2)] transition hover:bg-[var(--hover-strong)] disabled:opacity-40 disabled:hover:bg-[var(--hover)]"
        >
          {t('ide.browserGo')}
        </button>
      </form>

      {error && (
        <p
          role="alert"
          className="border-b border-[var(--border)] bg-red-500/10 px-3 py-1.5 text-[12px] text-[var(--danger)]"
        >
          {error}
        </p>
      )}

      <div
        ref={containerRef}
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-[var(--bg)]"
      >
        <canvas
          ref={canvasRef}
          width={1280}
          height={720}
          style={{ touchAction: 'none' }}
          onPointerMove={onPointerMove}
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onWheel={onWheel}
          onContextMenu={(event) => event.preventDefault()}
          className="block cursor-default outline-none"
        />
        <textarea
          ref={inputRef}
          aria-hidden="true"
          tabIndex={-1}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          onInput={onInput}
          onCompositionEnd={onCompositionEnd}
          onKeyDown={onKeyDown}
          onKeyUp={onKeyUp}
          className="absolute h-px w-px resize-none overflow-hidden border-0 bg-transparent p-0 text-transparent opacity-0 outline-none"
          style={{ left: caret.left, top: caret.top }}
        />
        {connection !== 'open' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[var(--bg)]/80 text-center">
            <p className="text-sm text-[var(--muted)]">
              {connection === 'connecting'
                ? t('ide.browserConnecting')
                : t('ide.browserDisconnected')}
            </p>
            {connection === 'closed' && (
              <button
                type="button"
                onClick={() => {
                  fatalRef.current = false
                  setError(null)
                  setReconnectNonce((value) => value + 1)
                }}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-[12px] font-medium text-white transition hover:bg-indigo-500"
              >
                {t('ide.browserReconnect')}
              </button>
            )}
          </div>
        )}
      </div>

      <p className="border-t border-[var(--border)] px-3 py-1 text-[11px] text-[var(--muted-3)]">
        {t('ide.browserHint')}
      </p>
    </div>
  )
}
