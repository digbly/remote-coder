import { memo } from 'react'
import { vscodeUrl } from '../../lib/api'

export const VSCodePanel = memo(function VSCodePanel({
  projectId,
  worktree,
  title,
}: {
  projectId: number
  worktree: string
  title: string
}) {
  return (
    <iframe
      title={title}
      src={vscodeUrl(projectId, worktree)}
      className="h-full w-full border-0 bg-[var(--bg)]"
      allow="clipboard-read; clipboard-write; fullscreen"
    />
  )
})
