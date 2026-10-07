import { useTranslation } from 'react-i18next'
import { buildCommand } from '../../lib/mock'
import { AutomationsIcon, ChevronDownIcon, CommandIcon } from './icons'

export function AgentPanel() {
  const { t } = useTranslation()

  return (
    <div className="shrink-0 border-t border-[#2c2e33] bg-[#161719] px-4 py-3 font-mono text-[12px]">
      <div className="flex items-center gap-2 text-[#7d828b]">
        <AutomationsIcon width={13} height={13} />
        <span>
          {t('ide.thought')}: <span className="text-[#9aa0a8]">266ms</span>
        </span>
      </div>

      <p className="mt-2 text-[#c2c6cc]">
        Now verify everything. First the backend:
      </p>

      <pre className="mt-2 overflow-x-auto rounded-md border border-[#2c2e33] bg-[#0f1012] px-3 py-2 text-[#c8ccd4]">
        <span className="text-[#6b7078]">:</span> {buildCommand}
      </pre>

      <div className="mt-3 flex items-center gap-3">
        <input
          type="text"
          aria-label={t('ide.prompt')}
          placeholder={t('ide.prompt')}
          className="min-w-0 flex-1 bg-transparent text-[13px] text-[#e6e8ec] outline-none placeholder:text-[#5a5f67]"
        />
        <span className="flex items-center gap-1 text-[11px] text-[#7d828b]">
          <CommandIcon width={12} height={12} />
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[#232529] pt-2.5 text-[11px] text-[#7d828b]">
        <span className="text-[#c2c6cc]">{t('ide.build')}</span>
        <span>{t('ide.buildAuto')}</span>
        <span className="text-[#5a5f67]">·</span>
        <span>DeepSeek V4.1 Flash</span>
        <span>OpenCode Go</span>
        <span className="text-[#5a5f67]">·</span>
        <span className="flex items-center gap-1 rounded bg-[#2a2c30] px-1.5 py-0.5 text-[#d7dae0]">
          low
          <ChevronDownIcon width={11} height={11} />
        </span>
      </div>
    </div>
  )
}
