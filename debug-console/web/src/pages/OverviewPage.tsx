import { useState, type ComponentType, type ReactNode } from 'react'
import { Box, Cpu, Trophy, Wifi, WifiOff } from 'lucide-react'
import { useAppState } from '../lib/store'
import { useNow } from '../lib/useNow'
import { formatRelative } from '../lib/time'
import { parseActiveEnvironment } from '../lib/env'
import { categoryVariant, challengeStatusVariant } from '../lib/badges'
import { cn } from '../lib/utils'
import type { Challenge } from '../lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { Skeleton } from '../components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import { ChallengeDrawer } from '../components/ChallengeDrawer'

interface OverviewPageProps {
  onOpenActivities: (sessionId: string) => void
}

function StatCard({
  title,
  icon: Icon,
  children,
}: {
  title: string
  icon: ComponentType<{ className?: string }>
  children: ReactNode
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-500">{title}</span>
          <Icon className="h-4 w-4 text-slate-400" />
        </div>
        <div className="mt-3">{children}</div>
      </CardContent>
    </Card>
  )
}

export function OverviewPage({ onOpenActivities }: OverviewPageProps) {
  const state = useAppState()
  useNow(1000)
  const [selected, setSelected] = useState<Challenge | null>(null)
  const { agent, snapshot, model } = state

  const challenges = snapshot?.challenges ?? []
  const slivers = snapshot?.slivers ?? []
  const solved = challenges.filter((c) => c.status === 'SOLVED').length
  const pct = challenges.length > 0 ? Math.round((solved / challenges.length) * 100) : 0
  const env = parseActiveEnvironment(snapshot?.environments_md)

  return (
    <div className="scroll-thin h-full overflow-auto">
      <div className="space-y-4 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard title="Agent 连接" icon={agent.agent_connected ? Wifi : WifiOff}>
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'h-2.5 w-2.5 rounded-full',
                  agent.agent_connected ? 'bg-emerald-500' : 'bg-red-500',
                )}
              />
              <span className="text-xl font-semibold">
                {agent.agent_connected ? '已连接' : '未连接'}
              </span>
            </div>
            <p className="mt-1 truncate text-xs text-slate-500">
              {agent.agent_hostname ?? '—'} · 最后活跃 {formatRelative(agent.last_seen)}
            </p>
          </StatCard>

          <StatCard title="题目进度" icon={Trophy}>
            <div className="text-xl font-semibold">
              {solved} <span className="text-sm font-normal text-slate-400">/ {challenges.length} 已解</span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </StatCard>

          <StatCard title="当前动态环境" icon={Box}>
            {env ? (
              <>
                <div className="text-xl font-semibold">题目 #{env.challengeId}</div>
                <p className="mt-1 truncate font-mono text-xs text-slate-500" title={env.entry}>
                  {env.entry}
                </p>
              </>
            ) : (
              <>
                <div className="text-xl font-semibold text-slate-400">无开启环境</div>
                <p className="mt-1 text-xs text-slate-500">动态环境池空闲</p>
              </>
            )}
          </StatCard>

          <StatCard title="当前模型" icon={Cpu}>
            <div className="truncate text-lg font-semibold" title={model.current ?? ''}>
              {model.current ?? '—'}
            </div>
            {model.pending ? (
              <p className="mt-1 truncate text-xs text-amber-600" title={model.pending}>
                待生效: {model.pending}
              </p>
            ) : (
              <p className="mt-1 text-xs text-slate-500">无待生效变更</p>
            )}
          </StatCard>
        </div>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>题目列表</CardTitle>
            <span className="text-xs text-slate-400">共 {challenges.length} 题</span>
          </CardHeader>
          <CardContent>
            {!snapshot ? (
              <div className="space-y-3">
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
                <p className="pt-2 text-center text-sm text-slate-400">
                  等待容器上报快照…
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">ID</TableHead>
                    <TableHead>名称</TableHead>
                    <TableHead>分类</TableHead>
                    <TableHead className="text-right">分值</TableHead>
                    <TableHead className="text-right">当前分</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead className="text-right">进行中 Sliver</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...challenges]
                    .sort((a, b) => a.id - b.id)
                    .map((c) => {
                      const activeSlivers = slivers.filter(
                        (s) => s.challenge_id === c.id && s.status !== 'finished',
                      ).length
                      return (
                        <TableRow
                          key={c.id}
                          className="cursor-pointer"
                          onClick={() => setSelected(c)}
                        >
                          <TableCell className="font-mono text-slate-500">{c.id}</TableCell>
                          <TableCell className="font-medium">{c.name}</TableCell>
                          <TableCell>
                            <Badge variant={categoryVariant(c.category)}>{c.category}</Badge>
                          </TableCell>
                          <TableCell className="text-right font-mono">{c.score}</TableCell>
                          <TableCell className="text-right font-mono">{c.current_score}</TableCell>
                          <TableCell>
                            <Badge variant={challengeStatusVariant(c.status)}>{c.status}</Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            {activeSlivers > 0 ? (
                              <span className="font-medium text-slate-700">{activeSlivers}</span>
                            ) : (
                              <span className="text-slate-300">—</span>
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  {challenges.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} className="py-10 text-center text-slate-400">
                        暂无题目数据
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <ChallengeDrawer
        challenge={selected}
        slivers={slivers}
        onClose={() => setSelected(null)}
        onOpenActivities={onOpenActivities}
      />
    </div>
  )
}
