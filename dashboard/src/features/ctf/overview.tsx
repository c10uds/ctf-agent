import { useCtfStore } from './store'
import { MetricsCards } from './metrics-cards'
import { LlmFeed } from './llm-feed'
import { EnvironmentsPanel } from './environments-panel'
import { statusClass } from './helpers'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

export function Overview() {
  const llm = useCtfStore((s) => s.llm)
  const workers = useCtfStore((s) => s.workers)
  const scoreboard = useCtfStore((s) => s.scoreboard)

  const solved = scoreboard.filter((r) => r.status.toUpperCase() === 'SOLVED').length
  const active = scoreboard.filter((r) =>
    ['ATTACKING', 'ANALYZING', 'LOCAL_READY', 'ENV_QUEUED'].includes(r.status.toUpperCase())
  ).length

  return (
    <div className='space-y-6'>
      <div className='flex flex-wrap items-center gap-3'>
        <h2 className='text-lg font-semibold'>总览</h2>
        <span className='text-muted-foreground text-sm'>
          已解 {solved} / {scoreboard.length} · 进行中 {active}
        </span>
      </div>

      <MetricsCards />

      <div className='grid gap-4 lg:grid-cols-2'>
        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='text-base'>Worker 进程</CardTitle>
          </CardHeader>
          <CardContent className='space-y-2'>
            {workers.length === 0 && (
              <div className='text-muted-foreground text-sm'>暂无 worker</div>
            )}
            {workers.map((w) => (
              <div
                key={w.id}
                className='flex items-center justify-between rounded-md border px-3 py-2 text-sm'
              >
                <div className='flex items-center gap-2'>
                  <Badge variant='outline' className='font-mono'>
                    #{w.id}
                  </Badge>
                  <Badge
                    variant='outline'
                    className={cn('font-mono text-[10px]', statusClass(w.alive ? 'ATTACKING' : 'STUCK'))}
                  >
                    {w.alive ? 'running' : 'dead'}
                  </Badge>
                </div>
                <div className='text-muted-foreground font-mono text-xs'>
                  pid {w.pid ?? '-'} · rss {w.rss ? `${Math.round(w.rss / 1048576)}MB` : '-'}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='text-base'>最近 AI 活动</CardTitle>
          </CardHeader>
          <CardContent>
            <LlmFeed events={llm.slice(0, 12)} empty='暂无 AI 请求' />
          </CardContent>
        </Card>
      </div>

      <EnvironmentsPanel />
    </div>
  )
}
