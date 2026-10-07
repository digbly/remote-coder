import { useTranslation } from 'react-i18next'
import { cost, diagnostics, memoryUsage, tokenUsage } from '../../lib/mock'

export function StatusBar() {
  const { t } = useTranslation()

  return (
    <div className="flex h-7 shrink-0 items-center justify-between border-t border-[#2c2e33] bg-[#1b1c1f] px-3 font-mono text-[11px] text-[#7d828b]">
      <div className="flex items-center gap-4">
        <span>{t('ide.interrupt')}</span>
        <span className="text-[#9aa0a8]" title={t('ide.tokensUsed')}>
          {tokenUsage}
        </span>
        <span className="text-[#9aa0a8]" title={t('ide.cost')}>
          {cost}
        </span>
      </div>

      <div className="flex items-center gap-4">
        <span>{t('ide.commands')}</span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#5a5f67]" />
          {t('ide.offline')}
        </span>
        <span title={t('ide.memory')}>{memoryUsage}</span>
        <span>{diagnostics.errors}</span>
        <span>{diagnostics.warnings}</span>
        <span className="flex items-center gap-1 text-[#c9a24a]">
          <span className="text-[#c9a24a]">⚠</span>
          {t('ide.workspaceConflict')}
        </span>
      </div>
    </div>
  )
}
