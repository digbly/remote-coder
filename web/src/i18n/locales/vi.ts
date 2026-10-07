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
  },
  dashboard: {
    greeting: 'Xin chào, {{username}}',
    status: 'Trạng thái: {{status}}',
    statusActive: 'Đang hoạt động',
    statusInactive: 'Không hoạt động',
    logout: 'Đăng xuất',
  },
  apiErrors: {
    invalidCredentials: 'Tên đăng nhập hoặc mật khẩu không đúng',
    inactiveUser: 'Tài khoản của bạn không hoạt động. Vui lòng liên hệ quản trị viên.',
    notAuthenticated: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
    csrfInvalid: 'Xác thực bảo mật thất bại. Vui lòng tải lại trang và thử lại.',
    rateLimited: 'Quá nhiều lần thử. Vui lòng thử lại sau.',
    validation: 'Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.',
    unknown: 'Đã có lỗi xảy ra. Vui lòng thử lại.',
  },
} as const

export default vi
