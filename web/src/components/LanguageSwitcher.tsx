import { useTranslation } from 'react-i18next'

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()
  const current = i18n.resolvedLanguage?.startsWith('vi') ? 'vi' : 'en'

  return (
    <select
      aria-label={t('language.label')}
      value={current}
      onChange={(event) => {
        void i18n.changeLanguage(event.target.value)
      }}
      className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-700 outline-none transition hover:bg-slate-100 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
    >
      <option value="vi">{t('language.vi')}</option>
      <option value="en">{t('language.en')}</option>
    </select>
  )
}
