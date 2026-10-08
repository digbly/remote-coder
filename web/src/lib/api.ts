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
  PROJECT_NOT_FOUND: 'apiErrors.projectNotFound',
  INVALID_GITHUB_URL: 'apiErrors.invalidGithubUrl',
  PROJECT_PATH_INVALID: 'apiErrors.projectPathInvalid',
  PROJECT_PATH_EXISTS: 'apiErrors.projectPathExists',
  PROJECT_NAME_EXISTS: 'apiErrors.projectNameExists',
  PROJECT_CLONE_FAILED: 'apiErrors.projectCloneFailed',
  GIT_NOT_A_REPOSITORY: 'apiErrors.gitNotARepository',
  GIT_COMMAND_FAILED: 'apiErrors.gitCommandFailed',
} as const

export interface User {
  id: number
  username: string
  is_active: boolean
}

export type ProjectSource = 'local' | 'github'

export interface Project {
  id: number
  name: string
  source: ProjectSource
  remote_url: string | null
  path: string
  created_at: string
}

export interface LocalProjectPayload {
  path: string
  name?: string
}

export interface GithubProjectPayload {
  repo_url: string
  name?: string
  token?: string
  branch?: string
}

export interface DirectoryEntry {
  name: string
  path: string
}

export interface DirectoryListing {
  root: string
  path: string
  parent: string | null
  directories: DirectoryEntry[]
}

export interface GitChange {
  path: string
  status: string
  orig_path: string | null
}

export interface GitStatus {
  branch: string | null
  upstream: string | null
  ahead: number
  behind: number
  staged: GitChange[]
  unstaged: GitChange[]
  untracked: string[]
  conflicted: string[]
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

export async function fetchProjects(): Promise<Project[]> {
  const response = await request('/projects')
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as Project[]
}

async function createProject(path: string, payload: unknown): Promise<Project> {
  const response = await request(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      [CSRF_HEADER]: readCookie(CSRF_COOKIE) ?? '',
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as Project
}

export function createLocalProject(payload: LocalProjectPayload): Promise<Project> {
  return createProject('/projects/local', payload)
}

export function createGithubProject(payload: GithubProjectPayload): Promise<Project> {
  return createProject('/projects/github', payload)
}

export async function browseDirectories(path?: string): Promise<DirectoryListing> {
  const query = path ? `?path=${encodeURIComponent(path)}` : ''
  const response = await request(`/projects/browse${query}`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as DirectoryListing
}

export async function fetchGitStatus(projectId: number): Promise<GitStatus> {
  const response = await request(`/projects/${projectId}/git/status`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as GitStatus
}

export function projectTerminalUrl(projectId: number): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${API_PREFIX}/projects/${projectId}/terminal`
}
