import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RequireAuth } from './components/RequireAuth'
import { LoginPage } from './routes/LoginPage'
import { WorkspaceLayout } from './routes/WorkspaceLayout'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: '/', element: <WorkspaceLayout /> },
      { path: '/projects/:projectId', element: <WorkspaceLayout /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
