export interface Worktree {
  id: string
  name: string
  primary?: boolean
  status?: string
  meta?: string
  active?: boolean
}

export interface Project {
  id: string
  name: string
  accent: string
  worktrees: Worktree[]
}

export const projects: Project[] = [
  {
    id: 'digbly',
    name: 'digbly',
    accent: 'text-violet-400',
    worktrees: [
      { id: 'digbly-develop', name: 'develop', primary: true },
      { id: 'digbly-dev', name: 'develop' },
    ],
  },
  {
    id: 'remote-coder',
    name: 'remote-coder',
    accent: 'text-sky-400',
    worktrees: [
      { id: 'rc-main', name: 'main', primary: true },
      { id: 'rc-main-oc', name: 'main', active: true, meta: '4m' },
    ],
  },
  {
    id: 'frontend',
    name: 'frontend',
    accent: 'text-emerald-400',
    worktrees: [{ id: 'fe-open', name: 'OpenCode', status: 'Idle', meta: 'now' }],
  },
]

export type TabKind = 'editor' | 'terminal' | 'app'

export interface Tab {
  id: string
  title: string
  kind: TabKind
}

export const tabs: Tab[] = [
  { id: 'tab-oc', title: 'OC | Hỗ trợ đa ngôn ngữ cho we...', kind: 'editor' },
  { id: 'tab-ssh', title: 'theanh@thuevpsgia...', kind: 'terminal' },
  { id: 'tab-app', title: 'Remote Coder', kind: 'app' },
  { id: 'tab-fish', title: 'fish /home/theanh/...', kind: 'terminal' },
]

export type DiffKind = 'context' | 'add' | 'del'

export interface DiffLine {
  kind: DiffKind
  oldNo: number | null
  newNo: number | null
  text: string
}

export const diffFileName = 'web/src/lib/api.ts'

export const diffLines: DiffLine[] = [
  { kind: 'context', oldNo: 63, newNo: 63, text: '  return (await response.json()) as User' },
  { kind: 'context', oldNo: 64, newNo: 64, text: '}' },
  { kind: 'context', oldNo: 65, newNo: 65, text: '' },
  { kind: 'context', oldNo: 66, newNo: 66, text: 'export async function fetchMe(): Promise<User> {' },
  { kind: 'context', oldNo: 67, newNo: 67, text: "  const response = await request('/auth/me')" },
  { kind: 'context', oldNo: 68, newNo: 68, text: '  if (!response.ok) {' },
  { kind: 'del', oldNo: 69, newNo: null, text: "    throw new Error(i18n.t('auth.notAuthenticated'))" },
  { kind: 'add', oldNo: null, newNo: 69, text: '    const data = await response.json().catch(() => null)' },
  {
    kind: 'add',
    oldNo: null,
    newNo: 70,
    text: "    throw new Error(extractError(data) ?? i18n.t('apiErrors.notAuthenticated'))",
  },
  { kind: 'context', oldNo: 70, newNo: 71, text: '  }' },
  { kind: 'context', oldNo: 71, newNo: 72, text: '  return (await response.json()) as User' },
  { kind: 'context', oldNo: 72, newNo: 73, text: '}' },
]

export type ChangeStatus = 'M' | 'A'

export interface ChangedFile {
  name: string
  path: string
  added: number
  removed: number
  status: ChangeStatus
}

export const unstagedChanges: ChangedFile[] = [
  { name: 'deps.py', path: 'app', added: 11, removed: 7, status: 'M' },
  { name: 'rate_limit.py', path: 'app', added: 5, removed: 3, status: 'M' },
  { name: 'auth.py', path: 'app/routers', added: 6, removed: 4, status: 'M' },
  { name: 'test_auth.py', path: 'tests', added: 32, removed: 0, status: 'M' },
  { name: 'App.tsx', path: 'web/src', added: 1, removed: 1, status: 'M' },
  { name: 'en.ts', path: 'web/src/i18n/locales', added: 8, removed: 3, status: 'M' },
  { name: 'vi.ts', path: 'web/src/i18n/locales', added: 8, removed: 3, status: 'M' },
  { name: 'api.ts', path: 'web/src/lib', added: 27, removed: 10, status: 'M' },
]

export const stagedChanges: ChangedFile[] = [
  { name: 'errors.py', path: 'app', added: 49, removed: 0, status: 'A' },
  { name: 'main.py', path: 'app', added: 4, removed: 0, status: 'M' },
  { name: 'auth.py', path: 'app/routers', added: 2, removed: 1, status: 'M' },
]

export const branch = 'main'
export const baseBranch = 'origin/main'
export const buildCommand = '.venv/bin/python -m pytest -q 2>&1 | tail -30'

export const tokenUsage = '96.1K (10%)'
export const cost = '$0.04'
export const memoryUsage = '806.6 MB'

export const diagnostics = { errors: 6, warnings: 0 }
