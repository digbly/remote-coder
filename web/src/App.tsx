import { RouterProvider } from 'react-router-dom'
import { AuthProvider } from './lib/auth'
import { ConfirmProvider } from './lib/confirm'
import { ThemeProvider } from './lib/theme'
import { router } from './router'

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ConfirmProvider>
          <RouterProvider router={router} />
        </ConfirmProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App
