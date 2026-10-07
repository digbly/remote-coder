import { useTranslation } from 'react-i18next'

export function LanguageSwitcher({ variant = 'light' }: { variant?: 'light' | 'dark' }) {
  const { t, i18n } = useTranslation()
  const current = i18n.resolvedLanguage?.startsWith('vi') ? 'vi' : 'en'

  const tone =
    variant === 'dark'
      ? 'border-[#33363b] bg-[#232529] text-[#c2c6cc] hover:bg-[#2a2c30] focus:border-indigo-500'
      : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200'

  return (
    <select
      aria-label={t('language.label')}
      value={current}
      onChange={(event) => {
        void i18n.changeLanguage(event.target.value)
      }}
      className={`rounded-lg border px-2 py-1.5 text-sm outline-none transition ${tone}`}
    >
      <option value="vi">{t('language.vi')}</option>
      <option value="en">{t('language.en')}</option>
    </select>
  )
}
