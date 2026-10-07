const en = {
  common: {
    appName: 'Remote Coder',
    loading: 'Loading...',
  },
  language: {
    label: 'Language',
    en: 'English',
    vi: 'Tiếng Việt',
  },
  login: {
    subtitle: 'Sign in to continue',
    username: 'Username',
    password: 'Password',
    submit: 'Sign in',
    submitting: 'Signing in...',
    error: 'Sign in failed',
  },
  dashboard: {
    greeting: 'Hello, {{username}}',
    status: 'Status: {{status}}',
    statusActive: 'Active',
    statusInactive: 'Inactive',
    logout: 'Log out',
  },
  auth: {
    notAuthenticated: 'Not signed in',
  },
} as const

export default en
