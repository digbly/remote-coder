import { diffFileName, diffLines, type DiffKind } from '../../lib/mock'
import { FileIcon } from './icons'

const lineClasses: Record<DiffKind, string> = {
  context: 'text-[#c8ccd4]',
  add: 'bg-[#1d3a2a] text-[#a6e3b8]',
  del: 'bg-[#3a2024] text-[#f0a9b0]',
}

export function EditorPane() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-auto bg-[#0f1012] font-mono text-[12.5px] leading-5">
      <div className="sticky top-0 flex items-center gap-2 border-b border-[#232529] bg-[#161719] px-3 py-1.5 text-[11px] text-[#8b9099]">
        <FileIcon width={13} height={13} />
        {diffFileName}
      </div>
      <div className="py-1.5">
        {diffLines.map((line, index) => (
          <div
            key={index}
            className={`flex whitespace-pre ${lineClasses[line.kind]}`}
          >
            <span className="w-12 shrink-0 select-none pr-3 text-right text-[#5a5f67]">
              {line.oldNo ?? ''}
            </span>
            <span className="w-12 shrink-0 select-none pr-3 text-right text-[#5a5f67]">
              {line.newNo ?? ''}
            </span>
            <span className="w-5 shrink-0 select-none text-center text-[#5a5f67]">
              {line.kind === 'add' ? '+' : line.kind === 'del' ? '-' : ''}
            </span>
            <span className="pr-4">{line.text || ' '}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
