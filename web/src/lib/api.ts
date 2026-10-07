import i18n from '../i18n'

const API_PREFIX = '/api/v1'
const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'

const ERROR_CODE_KEYS = {
  INVALID_CREDENTIALS: 'apiErrors.invalidCredentials',
  INACTIVE_USER: 'apiErrors.inactiveUser',
  NOT_AUTHENTICATED: 'apiErrors.notAuthenticated',
  CSRF_INVALID: 'apiErrors.csrfInvalid',
  RATE_LIMITED: 'apiErrors.rateLimited',
  VALIDATION_ERROR: 'apiErrors.validation',
} as const

export interface User {
  id: number
  username: string
  is_active: boolean
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

function isKnownErrorCode(code: string): code is keyof typeof ERROR_CODE_KEYS {
  return Object.hasOwn(ERROR_CODE_KEYS, code)
}

function extractError(data: unknown): string | null {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object' && 'code' in detail) {
      const code = (detail as { code: unknown }).code
      if (typeof code === 'string' && isKnownErrorCode(code)) {
        return i18n.t(ERROR_CODE_KEYS[code])
      }
      return i18n.t('apiErrors.unknown')
    }
  }
  return null
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('Accept-Language', i18n.resolvedLanguage ?? 'en')
  return fetch(`${API_PREFIX}${path}`, { credentials: 'include', ...init, headers })
}

export async function login(username: string, password: string): Promise<User> {
  const response = await request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }

  return (await response.json()) as User
}

export async function fetchMe(): Promise<User> {
  const response = await request('/auth/me')
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.notAuthenticated'))
  }
  return (await response.json()) as User
}

export async function logout(): Promise<void> {
  await request('/auth/logout', {
    method: 'POST',
    headers: { [CSRF_HEADER]: readCookie(CSRF_COOKIE) ?? '' },
  })
}
