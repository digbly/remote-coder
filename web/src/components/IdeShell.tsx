import type { User } from '../lib/api'
import { AgentPanel } from './ide/AgentPanel'
import { EditorPane } from './ide/EditorPane'
import { RightPanel } from './ide/RightPanel'
import { Sidebar } from './ide/Sidebar'
import { StatusBar } from './ide/StatusBar'
import { TopTabs } from './ide/TopTabs'

export function IdeShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0f1012] text-[#e6e8ec]">
      <Sidebar user={user} onLogout={onLogout} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopTabs />
        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <EditorPane />
            <AgentPanel />
          </div>
          <RightPanel />
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
