import { Activity, LayoutDashboard, MessageSquareText, Radar, Settings } from 'lucide-react'
import type { PageKey } from '../../lib/types'
import { useAppState } from '../../lib/store'
import { cn } from '../../lib/utils'
import { Separator } from '../ui/separator'

const NAV: { key: PageKey; label: string; icon: typeof LayoutDashboard }[] = [
  { key: 'overview', label: '题目总览', icon: LayoutDashboard },
  { key: 'activities', label: '会话活动', icon: Activity },
  { key: 'chat', label: '客服聊天', icon: MessageSquareText },
  { key: 'models', label: '模型设置', icon: Settings },
]

interface SidebarProps {
  page: PageKey
  onNavigate: (page: PageKey) => void
}

export function Sidebar({ page, onNavigate }: SidebarProps) {
  const state = useAppState()
  return (
    <aside className="flex w-60 shrink-0 flex-col bg-slate-950 text-slate-300">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <Radar className="h-6 w-6 text-emerald-400" />
        <div>
          <div className="text-sm font-semibold text-white">AIxCTF</div>
          <div className="text-xs text-slate-500">调试控制台</div>
        </div>
      </div>
      <Separator className="bg-slate-800" />
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => onNavigate(key)}
            className={cn(
              'flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors',
              page === key
                ? 'bg-slate-800 font-medium text-white'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200',
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>
      <div className="space-y-2 border-t border-slate-800 px-5 py-4 text-xs">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'h-2 w-2 rounded-full',
              state.wsConnected ? 'bg-emerald-500' : 'bg-red-500',
            )}
          />
          <span className="text-slate-400">控制台服务</span>
          <span className="ml-auto text-slate-500">{state.wsConnected ? '已连接' : '重连中'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'h-2 w-2 rounded-full',
              state.agent.agent_connected ? 'bg-emerald-500' : 'bg-red-500',
            )}
          />
          <span className="text-slate-400">容器 Agent</span>
          <span className="ml-auto text-slate-500">
            {state.agent.agent_connected ? '在线' : '离线'}
          </span>
        </div>
      </div>
    </aside>
  )
}
