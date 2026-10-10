import type { TabKind } from '../../lib/workspaceStore'

export const TAB_DOT_COLORS: Record<TabKind, string> = {
  terminal: 'bg-sky-400',
  editor: 'bg-indigo-400',
  vscode: 'bg-blue-400',
  chat: 'bg-emerald-400',
}
