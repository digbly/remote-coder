export interface LayoutState {
  leftOpen: boolean
  leftWidth: number
  rightOpen: boolean
  rightWidth: number
}

export const LEFT_MIN = 180
export const LEFT_MAX = 480
export const RIGHT_MIN = 260
export const RIGHT_MAX = 640

export const LAYOUT_DEFAULTS: LayoutState = {
  leftOpen: true,
  leftWidth: 240,
  rightOpen: true,
  rightWidth: 320,
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function clampWidth(value: unknown, fallback: number, min: number, max: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? clamp(value, min, max) : fallback
}

const LAYOUT_STORAGE_KEY = 'ide.layout'

export function loadLayout(): LayoutState {
  try {
    const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (raw === null) return { ...LAYOUT_DEFAULTS }
    return normalizeLayout(JSON.parse(raw))
  } catch {
    return { ...LAYOUT_DEFAULTS }
  }
}

export function saveLayout(layout: LayoutState): void {
  try {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout))
  } catch {
    /* storage unavailable */
  }
}

export function normalizeLayout(value: unknown): LayoutState {
  if (!isRecord(value)) return { ...LAYOUT_DEFAULTS }
  return {
    leftOpen: typeof value.leftOpen === 'boolean' ? value.leftOpen : LAYOUT_DEFAULTS.leftOpen,
    leftWidth: clampWidth(value.leftWidth, LAYOUT_DEFAULTS.leftWidth, LEFT_MIN, LEFT_MAX),
    rightOpen: typeof value.rightOpen === 'boolean' ? value.rightOpen : LAYOUT_DEFAULTS.rightOpen,
    rightWidth: clampWidth(value.rightWidth, LAYOUT_DEFAULTS.rightWidth, RIGHT_MIN, RIGHT_MAX),
  }
}
