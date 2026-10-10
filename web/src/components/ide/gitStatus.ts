import type { GitStatus } from '../../lib/api'

export const GIT_STATUS_REFRESH_INTERVAL_MS = 5000

export const GIT_STATUS_COLORS: Record<string, string> = {
  A: 'text-[var(--success)]',
  M: 'text-[var(--warn)]',
  D: 'text-[var(--danger-2)]',
  R: 'text-[var(--info)]',
  C: 'text-[var(--info)]',
  U: 'text-[var(--danger-2)]',
}

export function gitStatusColor(status: string): string {
  return GIT_STATUS_COLORS[status] ?? 'text-[var(--muted)]'
}

export function gitStatusSignature(status: GitStatus | null): string {
  return status ? JSON.stringify(status) : ''
}

const STATUS_PRIORITY = ['U', 'D', 'M', 'A', 'R', 'C']

function statusRank(status: string): number {
  const index = STATUS_PRIORITY.indexOf(status)
  return index === -1 ? STATUS_PRIORITY.length : index
}

export interface GitChangeMaps {
  files: Map<string, string>
  dirs: Map<string, string>
}

export function buildGitChangeMaps(status: GitStatus | null): GitChangeMaps {
  const files = new Map<string, string>()
  const dirs = new Map<string, string>()
  if (!status) return { files, dirs }

  const record = (map: Map<string, string>, key: string, value: string) => {
    const current = map.get(key)
    if (current === undefined || statusRank(value) < statusRank(current)) {
      map.set(key, value)
    }
  }

  for (const change of status.staged) record(files, change.path, change.status)
  for (const change of status.unstaged) record(files, change.path, change.status)
  for (const path of status.conflicted) record(files, path, 'U')
  for (const path of status.untracked) record(files, path, 'A')

  for (const [path, fileStatus] of files) {
    const parts = path.split('/')
    parts.pop()
    let prefix = ''
    for (const part of parts) {
      prefix = prefix ? `${prefix}/${part}` : part
      record(dirs, prefix, fileStatus)
    }
  }

  return { files, dirs }
}
