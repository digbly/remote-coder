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
  FILE_PATH_INVALID: 'apiErrors.filePathInvalid',
  FILE_NOT_FOUND: 'apiErrors.fileNotFound',
  FILE_TOO_LARGE: 'apiErrors.fileTooLarge',
  FILE_BINARY: 'apiErrors.fileBinary',
  FILE_WRITE_FAILED: 'apiErrors.fileWriteFailed',
  GIT_NOT_A_REPOSITORY: 'apiErrors.gitNotARepository',
  GIT_COMMAND_FAILED: 'apiErrors.gitCommandFailed',
  GIT_INVALID_PATH: 'apiErrors.gitInvalidPath',
  GIT_NOTHING_TO_COMMIT: 'apiErrors.gitNothingToCommit',
  GIT_REMOTE_MISSING: 'apiErrors.gitRemoteMissing',
  GIT_BRANCH_INVALID: 'apiErrors.gitBranchInvalid',
  GIT_PUSH_FAILED: 'apiErrors.gitPushFailed',
  GIT_PULL_REQUEST_FAILED: 'apiErrors.gitPullRequestFailed',
  GIT_DISCARD_FAILED: 'apiErrors.gitDiscardFailed',
  GIT_PULL_FAILED: 'apiErrors.gitPullFailed',
  GIT_NO_UPSTREAM: 'apiErrors.gitNoUpstream',
  VSCODE_DISABLED: 'apiErrors.vscodeDisabled',
  VSCODE_WORKTREE_NOT_FOUND: 'apiErrors.vscodeWorktreeNotFound',
  VSCODE_START_FAILED: 'apiErrors.vscodeStartFailed',
  VSCODE_PROXY_FAILED: 'apiErrors.vscodeProxyFailed',
  VSCODE_FORBIDDEN: 'apiErrors.vscodeForbidden',
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

export interface GitCommitResult {
  commit: string
  branch: string | null
}

export interface GitPullRequestResult {
  url: string
  branch: string
  base: string
}

export interface GitPullRequestSummary {
  number: number
  title: string
  url: string
  state: string
  is_draft: boolean
  head: string | null
  base: string | null
}

export interface GitPullRequestStatus {
  pull_request: GitPullRequestSummary | null
}

export interface FileNode {
  name: string
  path: string
  type: 'file' | 'directory'
  children: FileNode[]
}

export interface FileTree {
  entries: FileNode[]
  truncated: boolean
}

export interface FileContent {
  path: string
  content: string
  size: number
}

export interface GitBranches {
  current: string | null
  branches: string[]
}

export interface Worktree {
  name: string
  path: string
  branch: string | null
  is_primary: boolean
}

export interface AgentStatus {
  command: string
  installed: boolean
  path: string | null
}

export interface AgentSettingItem {
  agent_id: string
  command: string
  args: string
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
const NO_REFRESH_PATHS = new Set(['/auth/login', '/auth/refresh'])

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

function buildHeaders(init: HeadersInit | undefined, method: string): Headers {
  const headers = new Headers(init)
  headers.set('Accept-Language', i18n.resolvedLanguage ?? 'en')
  if (!SAFE_METHODS.has(method.toUpperCase())) {
    headers.set(CSRF_HEADER, readCookie(CSRF_COOKIE) ?? '')
  }
  return headers
}

let refreshPromise: Promise<boolean> | null = null

async function rotateSession(): Promise<boolean> {
  const run = () =>
    fetch(`${API_PREFIX}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: buildHeaders(undefined, 'POST'),
    })
      .then((response) => response.ok)
      .catch(() => false)

  // Serialize across tabs so a concurrent refresh sends the rotated cookie
  // instead of replaying the previous one (which the server treats as theft).
  return navigator.locks ? navigator.locks.request('auth-refresh', run) : run()
}

export function refreshSession(): Promise<boolean> {
  refreshPromise ??= rotateSession().finally(() => {
    refreshPromise = null
  })
  return refreshPromise
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
  const method = init.method ?? 'GET'
  const send = () =>
    fetch(`${API_PREFIX}${path}`, {
      credentials: 'include',
      ...init,
      headers: buildHeaders(init.headers, method),
    })

  const response = await send()
  if (response.status === 401 && !NO_REFRESH_PATHS.has(path) && (await refreshSession())) {
    return send()
  }

  return response
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
  await request('/auth/logout', { method: 'POST' })
}

export async function fetchProjects(): Promise<Project[]> {
  const response = await request('/projects')
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as Project[]
}

export async function fetchProject(projectId: number): Promise<Project> {
  const response = await request(`/projects/${projectId}`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const fallbackKey = response.status === 404 ? 'apiErrors.projectNotFound' : 'apiErrors.unknown'
    throw new Error(extractError(data) ?? i18n.t(fallbackKey))
  }
  return (await response.json()) as Project
}

async function createProject(path: string, payload: unknown): Promise<Project> {
  const response = await request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as T
}

export function stagePaths(projectId: number, paths: string[]): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/stage`, { paths })
}

export function unstagePaths(projectId: number, paths: string[]): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/unstage`, { paths })
}

export function stageAllPaths(projectId: number): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/stage-all`, {})
}

export function unstageAllPaths(projectId: number): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/unstage-all`, {})
}

export function discardPaths(projectId: number, paths: string[]): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/discard`, { paths })
}

export function pushBranch(projectId: number): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/push`, {})
}

export function pullBranch(projectId: number): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/pull`, {})
}

export async function fetchBranches(projectId: number): Promise<GitBranches> {
  const response = await request(`/projects/${projectId}/git/branches`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as GitBranches
}

export function createBranch(projectId: number, name: string): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/branches`, { name })
}

export function checkoutBranch(projectId: number, name: string): Promise<GitStatus> {
  return postJson(`/projects/${projectId}/git/checkout`, { name })
}

export function commitChanges(projectId: number, message: string): Promise<GitCommitResult> {
  return postJson(`/projects/${projectId}/git/commit`, { message })
}

export function createPullRequest(
  projectId: number,
  branch: string,
): Promise<GitPullRequestResult> {
  return postJson(`/projects/${projectId}/git/pull-request`, { branch })
}

export async function fetchCurrentPullRequest(projectId: number): Promise<GitPullRequestStatus> {
  const response = await request(`/projects/${projectId}/git/pull-request`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as GitPullRequestStatus
}

export async function fetchFileTree(projectId: number): Promise<FileTree> {
  const response = await request(`/projects/${projectId}/files`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as FileTree
}

export async function fetchFileContent(projectId: number, path: string): Promise<FileContent> {
  const query = `?path=${encodeURIComponent(path)}`
  const response = await request(`/projects/${projectId}/file${query}`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as FileContent
}

export async function saveFileContent(
  projectId: number,
  path: string,
  content: string,
): Promise<FileContent> {
  const response = await request(`/projects/${projectId}/file`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as FileContent
}

export async function fetchWorktrees(projectId: number): Promise<Worktree[]> {
  const response = await request(`/projects/${projectId}/git/worktrees`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as Worktree[]
}

export async function detectAgents(commands: string[]): Promise<AgentStatus[]> {
  const query = encodeURIComponent(commands.join(','))
  const response = await request(`/agents?commands=${query}`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const data = (await response.json()) as { agents: AgentStatus[] }
  return data.agents
}

export interface TerminalUrlOptions {
  worktree?: string
  agent?: string
}

export async function fetchAgentSettings(): Promise<AgentSettingItem[]> {
  const response = await request('/agents/settings')
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const data = (await response.json()) as { settings: AgentSettingItem[] }
  return data.settings
}

export async function saveAgentSetting(
  agentId: string,
  command: string,
  args: string,
): Promise<AgentSettingItem> {
  const response = await request(`/agents/settings/${encodeURIComponent(agentId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, args }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as AgentSettingItem
}

export function projectTerminalUrl(
  projectId: number,
  terminalId: string,
  options: TerminalUrlOptions = {},
): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const params = new URLSearchParams()
  if (options.worktree) params.set('worktree', options.worktree)
  if (options.agent) params.set('agent', options.agent)
  const search = params.toString()
  const query = search ? `?${search}` : ''
  return `${protocol}//${window.location.host}${API_PREFIX}/projects/${projectId}/terminal/${encodeURIComponent(terminalId)}${query}`
}

export function vscodeUrl(projectId: number, worktree: string): string {
  return `${API_PREFIX}/projects/${projectId}/vscode/${encodeURIComponent(worktree)}/`
}

export function workspaceUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${API_PREFIX}/workspace/ws`
}

export async function killTerminal(projectId: number, terminalId: string): Promise<void> {
  await request(`/projects/${projectId}/terminal/${encodeURIComponent(terminalId)}`, {
    method: 'DELETE',
  })
}
