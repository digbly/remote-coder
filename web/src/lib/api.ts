import i18n from '../i18n'

const API_PREFIX = '/api/v1'
const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'

export interface User {
  id: number
  username: string
  is_active: boolean
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

function extractError(data: unknown, fallback: string): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const first = detail[0]
      if (first && typeof first === 'object' && 'msg' in first && typeof first.msg === 'string') {
        return first.msg
      }
    }
  }
  return fallback
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_PREFIX}${path}`, { credentials: 'include', ...init })
}

export async function login(username: string, password: string): Promise<User> {
  const response = await request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data, i18n.t('login.error')))
  }

  return (await response.json()) as User
}

export async function fetchMe(): Promise<User> {
  const response = await request('/auth/me')
  if (!response.ok) {
    throw new Error(i18n.t('auth.notAuthenticated'))
  }
  return (await response.json()) as User
}

export async function logout(): Promise<void> {
  await request('/auth/logout', {
    method: 'POST',
    headers: { [CSRF_HEADER]: readCookie(CSRF_COOKIE) ?? '' },
  })
}
