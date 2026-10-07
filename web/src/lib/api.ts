const API_PREFIX = '/api/v1'
const TOKEN_KEY = 'rc_token'

export interface User {
  id: number
  username: string
  is_active: boolean
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export async function login(username: string, password: string): Promise<string> {
  const response = await fetch(`${API_PREFIX}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(data?.detail ?? 'Đăng nhập thất bại')
  }

  const data = await response.json()
  return data.access_token as string
}

export async function fetchMe(token: string): Promise<User> {
  const response = await fetch(`${API_PREFIX}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    throw new Error('Phiên đăng nhập đã hết hạn')
  }

  return (await response.json()) as User
}
