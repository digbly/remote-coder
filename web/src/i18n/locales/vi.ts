const vi = {
  common: {
    appName: 'Remote Coder',
    loading: 'Đang tải...',
  },
  language: {
    label: 'Ngôn ngữ',
    en: 'English',
    vi: 'Tiếng Việt',
  },
  login: {
    subtitle: 'Đăng nhập để tiếp tục',
    username: 'Tên đăng nhập',
    password: 'Mật khẩu',
    submit: 'Đăng nhập',
    submitting: 'Đang đăng nhập...',
    error: 'Đăng nhập thất bại',
  },
  dashboard: {
    greeting: 'Xin chào, {{username}}',
    status: 'Trạng thái: {{status}}',
    statusActive: 'Đang hoạt động',
    statusInactive: 'Không hoạt động',
    logout: 'Đăng xuất',
  },
  auth: {
    notAuthenticated: 'Chưa đăng nhập',
  },
} as const

export default vi
