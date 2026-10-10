const PANEL_TABS = ['explorer', 'sourceControl', 'check'] as const

export type PanelTab = (typeof PANEL_TABS)[number]

const STORAGE_KEY = 'ide.panelTab'
const DEFAULT_PANEL_TAB: PanelTab = 'explorer'

function isPanelTab(value: unknown): value is PanelTab {
  return typeof value === 'string' && (PANEL_TABS as readonly string[]).includes(value)
}

function readStore(): Record<string, PanelTab> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw === null) return {}
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const result: Record<string, PanelTab> = {}
    for (const [key, value] of Object.entries(parsed)) {
      if (isPanelTab(value)) result[key] = value
    }
    return result
  } catch {
    return {}
  }
}

export function loadPanelTab(projectId: number): PanelTab {
  return readStore()[String(projectId)] ?? DEFAULT_PANEL_TAB
}

export function savePanelTab(projectId: number, tab: PanelTab): void {
  try {
    const store = readStore()
    store[String(projectId)] = tab
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    /* storage unavailable */
  }
}
