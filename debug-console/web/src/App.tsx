import { useEffect, useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { socket } from './lib/ws'
import { store, useAppState } from './lib/store'
import type { PageKey } from './lib/types'
import { Sidebar } from './components/layout/Sidebar'
import { Header } from './components/layout/Header'
import { OverviewPage } from './pages/OverviewPage'
import { ActivitiesPage } from './pages/ActivitiesPage'
import { ChatPage } from './pages/ChatPage'
import { ModelsPage } from './pages/ModelsPage'

export default function App() {
  const [page, setPage] = useState<PageKey>('overview')
  const [activitySession, setActivitySession] = useState<string | null>(null)
  const state = useAppState()

  useEffect(() => {
    socket.connect()
  }, [])

  const openActivities = (sessionId: string) => {
    setActivitySession(sessionId)
    setPage('activities')
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      <Sidebar page={page} onNavigate={setPage} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header page={page} />
        {state.lastError && (
          <div className="flex items-center gap-2 border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="flex-1">{state.lastError.message}</span>
            <button
              onClick={() => store.dismissError()}
              aria-label="关闭"
              className="text-red-400 hover:text-red-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <main className="min-h-0 flex-1">
          {page === 'overview' && <OverviewPage onOpenActivities={openActivities} />}
          {page === 'activities' && (
            <ActivitiesPage sessionId={activitySession} onSessionChange={setActivitySession} />
          )}
          {page === 'chat' && <ChatPage />}
          {page === 'models' && <ModelsPage />}
        </main>
      </div>
    </div>
  )
}
