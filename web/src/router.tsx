import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RequireAuth } from './components/RequireAuth'
import { LoginPage } from './routes/LoginPage'
import { SettingsPage } from './routes/SettingsPage'
import { WorkspaceLayout } from './routes/WorkspaceLayout'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: '/', element: <WorkspaceLayout /> },
      { path: '/projects/:projectId', element: <WorkspaceLayout /> },
      { path: '/settings', element: <Navigate to="/settings/appearance" replace /> },
      { path: '/settings/:section', element: <SettingsPage /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
