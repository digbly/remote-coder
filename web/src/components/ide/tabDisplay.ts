import type { TabKind } from '../../lib/workspaceStore'

export const TAB_DOT_COLORS: Record<TabKind, string> = {
  terminal: 'bg-sky-400',
  editor: 'bg-indigo-400',
  vscode: 'bg-blue-400',
  chat: 'bg-emerald-400',
  diff: 'bg-amber-400',
  browser: 'bg-rose-400',
}

export interface TabColor {
  key: string
  value: string
}

// The palette a tab can be tagged with from the context menu. Colors are stored
// by key so the sync payload stays small, and resolved to a value for rendering.
export const TAB_COLORS: TabColor[] = [
  { key: 'blue', value: '#3b82f6' },
  { key: 'violet', value: '#8b5cf6' },
  { key: 'pink', value: '#ec4899' },
  { key: 'red', value: '#ef4444' },
  { key: 'orange', value: '#f97316' },
  { key: 'amber', value: '#f59e0b' },
  { key: 'green', value: '#22c55e' },
  { key: 'teal', value: '#14b8a6' },
  { key: 'slate', value: '#64748b' },
]

export function tabColorValue(color: string | undefined): string | undefined {
  if (!color) return undefined
  return TAB_COLORS.find((entry) => entry.key === color)?.value
}
