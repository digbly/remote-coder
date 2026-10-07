import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'
import en from './locales/en'
import vi from './locales/vi'

export const resources = {
  en: { translation: en },
  vi: { translation: vi },
} as const

export const supportedLanguages = ['en', 'vi'] as const

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: [...supportedLanguages],
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'remote-coder.lang',
    },
  })

function applyDocumentLang(language: string | undefined) {
  document.documentElement.lang = language ?? 'en'
}

applyDocumentLang(i18n.resolvedLanguage)
i18n.on('languageChanged', applyDocumentLang)

export default i18n
