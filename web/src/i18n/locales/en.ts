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
  },
  dashboard: {
    greeting: 'Hello, {{username}}',
    status: 'Status: {{status}}',
    statusActive: 'Active',
    statusInactive: 'Inactive',
    logout: 'Log out',
  },
  apiErrors: {
    invalidCredentials: 'Incorrect username or password',
    inactiveUser: 'Your account is inactive. Please contact an administrator.',
    notAuthenticated: 'Your session has expired. Please sign in again.',
    csrfInvalid: 'Security check failed. Please refresh and try again.',
    rateLimited: 'Too many attempts. Please try again later.',
    validation: 'Invalid input. Please check the form and try again.',
    unknown: 'Something went wrong. Please try again.',
  },
} as const

export default en
