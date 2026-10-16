import type { PageKey } from '../../lib/types'
import { useAppState } from '../../lib/store'
import { useNow } from '../../lib/useNow'
import { formatRelative } from '../../lib/time'
import { cn } from '../../lib/utils'

const TITLES: Record<PageKey, { title: string; desc: string }> = {
  overview: { title: '题目总览', desc: '比赛进度与题目状态一览' },
  activities: { title: '会话活动', desc: 'Master / Sliver 的 API 请求记录' },
  chat: { title: '客服聊天', desc: '与容器内 CTF-Customer 对话' },
  models: { title: '模型设置', desc: '查看与切换 Master 使用的模型' },
}

export function Header({ page }: { page: PageKey }) {
  const { agent } = useAppState()
  useNow(1000)
  const { title, desc } = TITLES[page]
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div>
        <h1 className="text-base font-semibold text-slate-900">{title}</h1>
        <p className="text-xs text-slate-500">{desc}</p>
      </div>
      <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs">
        <span
          className={cn(
            'h-2 w-2 rounded-full',
            agent.agent_connected ? 'bg-emerald-500' : 'bg-red-500',
          )}
        />
        <span className="font-medium text-slate-700">
          {agent.agent_connected ? 'Agent 在线' : 'Agent 离线'}
        </span>
        {agent.agent_hostname && (
          <span className="text-slate-400">{agent.agent_hostname}</span>
        )}
        <span className="text-slate-400">· 最后活跃 {formatRelative(agent.last_seen)}</span>
      </div>
    </header>
  )
}
