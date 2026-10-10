import i18n from '../i18n'
import type { AgentDefinition } from './agents'

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
  SEARCH_QUERY_INVALID: 'apiErrors.searchQueryInvalid',
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
  GIT_WORKTREE_INVALID: 'apiErrors.gitWorktreeInvalid',
  GIT_WORKTREE_EXISTS: 'apiErrors.gitWorktreeExists',
  GIT_WORKTREE_FAILED: 'apiErrors.gitWorktreeFailed',
  GIT_WORKTREE_NOT_FOUND: 'apiErrors.gitWorktreeNotFound',
  GIT_WORKTREE_DELETE_FAILED: 'apiErrors.gitWorktreeDeleteFailed',
  AGENT_NOT_FOUND: 'apiErrors.agentNotFound',
  AGENT_NOT_CONFIGURED: 'apiErrors.agentNotConfigured',
  AGENT_UNSUPPORTED: 'apiErrors.agentUnsupported',
  AGENT_GENERATE_FAILED: 'apiErrors.agentGenerateFailed',
  AI_PROVIDER_NOT_FOUND: 'apiErrors.aiProviderNotFound',
  AI_PROVIDER_ADMIN_REQUIRED: 'apiErrors.aiProviderAdminRequired',
  AI_PROVIDER_NAME_EXISTS: 'apiErrors.aiProviderNameExists',
  AI_PROVIDER_FAILED: 'apiErrors.aiProviderFailed',
  AI_CREDENTIAL_ENCRYPTION_UNAVAILABLE: 'apiErrors.aiCredentialEncryptionUnavailable',
  AI_CHAT_CONVERSATION_NOT_FOUND: 'apiErrors.aiChatConversationNotFound',
  AI_CHAT_MODEL_UNAVAILABLE: 'apiErrors.aiChatModelUnavailable',
  AI_CHAT_LIMIT_EXCEEDED: 'apiErrors.aiChatLimitExceeded',
  AI_COMMAND_APPROVAL_NOT_FOUND: 'apiErrors.aiCommandApprovalNotFound',
  AI_CHANGE_PROPOSAL_NOT_FOUND: 'apiErrors.aiChangeProposalNotFound',
  AI_CHANGE_PROPOSAL_NOT_PENDING: 'apiErrors.aiChangeProposalNotPending',
  AI_CHANGE_PROPOSAL_STALE: 'apiErrors.aiChangeProposalStale',
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

export interface GitCommitMessageResult {
  message: string
  agent_id: string
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

export type FileSearchMode = 'names' | 'contents'

export interface SearchSpan {
  start: number
  end: number
}

export interface FileSearchMatch {
  line: number
  text: string
  spans: SearchSpan[]
}

export interface FileSearchEntry {
  path: string
  matches: FileSearchMatch[]
  spans: SearchSpan[]
}

export interface FileSearchResult {
  entries: FileSearchEntry[]
  truncated: boolean
}

export interface FileSearchOptions {
  mode: FileSearchMode
  include?: string
  exclude?: string
  caseSensitive?: boolean
  wholeWord?: boolean
  regex?: boolean
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

export interface WorktreeCreatePayload {
  name: string
  branch: string
  create_branch: boolean
}

export interface AgentSettingItem {
  agent_id: string
  command: string
  args: string
  commit_args: string
}

export interface AgentSettingsInfo {
  default_agent_id: string | null
}

export type AIProviderKind = 'openai' | 'anthropic' | 'gemini'

export interface AIProvider {
  id: number
  name: string
  kind: AIProviderKind
  shared: boolean
  credential_configured: boolean
  created_at: string
}

export interface AIProviderList {
  providers: AIProvider[]
  can_manage_shared: boolean
}

export interface AIProviderModel {
  id: string
  display_name: string
}

export interface AIProviderPayload {
  name: string
  kind: AIProviderKind
  api_key: string
}

export interface AIProviderUpdate {
  name?: string
  api_key?: string
}

export interface AIChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  thinking: string
  error?: string
  notice?: string
  steps?: string[]
  status: 'streaming' | 'completed' | 'failed' | 'interrupted'
  created_at: string
}

export interface AIConversation {
  id: string
  project_id: number
  provider_id: number | null
  model_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface AIConversationDetail {
  conversation: AIConversation
  messages: AIChatMessage[]
}

export type AIProposalChangeType =
  | 'modify'
  | 'create'
  | 'delete'
  | 'create_directory'
  | 'delete_directory'
  | 'move'

export interface AIChangeProposal {
  id: string
  conversation_id: string
  path: string
  target_path: string | null
  change_type: AIProposalChangeType
  diff: string
  status: 'pending' | 'applied' | 'rejected' | 'stale'
  created_at: string
  updated_at: string
}

export type AICommandPermission = 'manual' | 'risky' | 'allow_all'

export async function fetchAICommandPermission(projectId: number): Promise<AICommandPermission> {
  const response = await request(`/projects/${projectId}/ai-chat/command-permission`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const result = (await response.json()) as { mode: AICommandPermission }
  return result.mode
}

export async function updateAICommandPermission(
  projectId: number,
  mode: AICommandPermission,
): Promise<AICommandPermission> {
  const response = await request(`/projects/${projectId}/ai-chat/command-permission`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const result = (await response.json()) as { mode: AICommandPermission }
  return result.mode
}

export async function decideAICommand(
  projectId: number,
  approvalId: string,
  approved: boolean,
): Promise<void> {
  const response = await request(
    `/projects/${projectId}/ai-chat/commands/${encodeURIComponent(approvalId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved }),
    },
  )
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
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

export function generateCommitMessage(projectId: number): Promise<GitCommitMessageResult> {
  return postJson(`/projects/${projectId}/git/commit-message`, {})
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

export async function fetchFileTree(projectId: number, path?: string): Promise<FileTree> {
  const query = path ? `?path=${encodeURIComponent(path)}` : ''
  const response = await request(`/projects/${projectId}/files${query}`)
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

export async function searchProjectFiles(
  projectId: number,
  query: string,
  options: FileSearchOptions,
): Promise<FileSearchResult> {
  const params = new URLSearchParams({ q: query, mode: options.mode })
  if (options.include) params.set('include', options.include)
  if (options.exclude) params.set('exclude', options.exclude)
  if (options.caseSensitive) params.set('case_sensitive', 'true')
  if (options.wholeWord) params.set('whole_word', 'true')
  if (options.regex) params.set('regex', 'true')
  const response = await request(`/projects/${projectId}/search?${params.toString()}`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as FileSearchResult
}

export async function fetchWorktrees(projectId: number): Promise<Worktree[]> {
  const response = await request(`/projects/${projectId}/git/worktrees`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as Worktree[]
}

export function createWorktree(
  projectId: number,
  payload: WorktreeCreatePayload,
): Promise<Worktree> {
  return postJson(`/projects/${projectId}/git/worktrees`, payload)
}

export async function deleteWorktree(projectId: number, name: string): Promise<void> {
  const response = await request(
    `/projects/${projectId}/git/worktrees/${encodeURIComponent(name)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
}

export async function fetchAgents(): Promise<AgentDefinition[]> {
  const response = await request('/agents')
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const data = (await response.json()) as { agents: AgentDefinition[] }
  return data.agents
}

export interface TerminalUrlOptions {
  worktree?: string
  agentId?: string
}

export async function saveAgentSetting(
  agentId: string,
  command: string,
  args: string,
  commitArgs: string,
): Promise<AgentSettingItem> {
  const response = await request(`/agents/settings/${encodeURIComponent(agentId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, args, commit_args: commitArgs }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as AgentSettingItem
}

export async function fetchAgentSettings(): Promise<AgentSettingsInfo> {
  const response = await request('/agents/settings')
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as AgentSettingsInfo
}

export async function fetchAIProviders(): Promise<AIProviderList> {
  const response = await request('/ai-providers')
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as AIProviderList
}

export async function createAIProvider(
  payload: AIProviderPayload,
  shared = false,
): Promise<AIProvider> {
  return postJson(`/ai-providers${shared ? '/shared' : ''}`, payload)
}

export async function updateAIProvider(
  providerId: number,
  payload: AIProviderUpdate,
  shared = false,
): Promise<AIProvider> {
  const response = await request(
    `/ai-providers${shared ? `/shared/${providerId}` : `/${providerId}`}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as AIProvider
}

export async function deleteAIProvider(providerId: number, shared = false): Promise<void> {
  const response = await request(
    `/ai-providers${shared ? `/shared/${providerId}` : `/${providerId}`}`,
    { method: 'DELETE' },
  )
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
}

export async function fetchAIProviderModels(providerId: number): Promise<AIProviderModel[]> {
  const response = await request(`/ai-providers/${providerId}/models`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const result = (await response.json()) as { models: AIProviderModel[] }
  return result.models
}

export async function fetchAIConversations(projectId: number): Promise<AIConversation[]> {
  const response = await request(`/projects/${projectId}/ai-chat/conversations`)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const result = (await response.json()) as { conversations: AIConversation[] }
  return result.conversations
}

export async function fetchAIConversation(
  projectId: number,
  conversationId: string,
): Promise<AIConversationDetail> {
  const response = await request(
    `/projects/${projectId}/ai-chat/conversations/${encodeURIComponent(conversationId)}`,
  )
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as AIConversationDetail
}

export async function fetchAIProposals(
  projectId: number,
  conversationId: string,
): Promise<AIChangeProposal[]> {
  const response = await request(
    `/projects/${projectId}/ai-chat/conversations/${encodeURIComponent(conversationId)}/proposals`,
  )
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const result = (await response.json()) as { proposals: AIChangeProposal[] }
  return result.proposals
}

export async function updateAIProposal(
  projectId: number,
  conversationId: string,
  proposalId: string,
  action: 'apply' | 'reject',
): Promise<AIChangeProposal> {
  const response = await request(
    `/projects/${projectId}/ai-chat/conversations/${encodeURIComponent(conversationId)}/proposals/${encodeURIComponent(proposalId)}/${action}`,
    { method: 'POST' },
  )
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const result = (await response.json()) as { proposal: AIChangeProposal }
  return result.proposal
}

export async function openAIChatStream(
  projectId: number,
  payload: {
    conversation_id: string | null
    provider_id: number
    model_id: string
    message: string
  },
  signal: AbortSignal,
): Promise<Response> {
  const response = await request(`/projects/${projectId}/ai-chat/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  if (!response.body) throw new Error(i18n.t('apiErrors.unknown'))
  return response
}

export async function setDefaultAgent(agentId: string | null): Promise<AgentSettingsInfo> {
  const response = await request('/agents/default', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  return (await response.json()) as AgentSettingsInfo
}

export function projectTerminalUrl(
  projectId: number,
  terminalId: string,
  options: TerminalUrlOptions = {},
): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const params = new URLSearchParams()
  if (options.worktree) params.set('worktree', options.worktree)
  if (options.agentId) params.set('agent_id', options.agentId)
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

export async function fetchRunningTerminals(): Promise<Record<number, string[]>> {
  const response = await request('/terminals/running')
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(extractError(data) ?? i18n.t('apiErrors.unknown'))
  }
  const data = (await response.json()) as { projects?: Record<string, string[]> }
  const result: Record<number, string[]> = {}
  for (const [key, value] of Object.entries(data.projects ?? {})) {
    result[Number(key)] = value
  }
  return result
}
