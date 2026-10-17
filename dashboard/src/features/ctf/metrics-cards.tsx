import { useCtfStore } from './store'
import { formatBytes, formatUptime } from './helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardTitle className='text-muted-foreground text-xs font-medium'>{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className='text-2xl font-semibold'>{value}</div>
        {hint && <div className='text-muted-foreground mt-1 text-xs'>{hint}</div>}
      </CardContent>
    </Card>
  )
}

export function MetricsCards() {
  const metrics = useCtfStore((s) => s.metrics)
  const container = useCtfStore((s) => s.container)
  const connected = useCtfStore((s) => s.connected)

  // 内存优先看容器 cgroup 账本；拿不到才退回宿主机数字（并明确标注"宿主机"）
  const cg = metrics?.cgroup_mem
  const cgLimit = cg?.limit ?? 0
  const memUsed = cg?.current ? cg.current : (metrics?.mem_used ?? 0)
  const memTotal = cgLimit || metrics?.mem_total || 0
  const memPct = memTotal ? (memUsed / memTotal) * 100 : 0
  const memHint = metrics
    ? cgLimit
      ? `容器限额 ${formatBytes(cgLimit)} · 已用 ${memPct.toFixed(0)}%`
      : `宿主机 共 ${formatBytes(memTotal)} · 已用 ${memPct.toFixed(0)}%`
    : undefined

  const diskPct =
    metrics && metrics.disk?.total ? (metrics.disk.used / metrics.disk.total) * 100 : 0

  // 容器存活时间以 forwarder 上线时间算；/proc/uptime 是宿主机的，会误标成"容器运行 18h"
  const aliveSec =
    container?.started_at != null ? Math.max(0, Date.now() / 1000 - container.started_at) : undefined

  return (
    <div className='space-y-4'>
      <div className='flex items-center gap-2'>
        <span
          className={cn(
            'inline-block size-2.5 rounded-full',
            connected ? 'bg-emerald-500' : 'bg-rose-500'
          )}
        />
        <span className='text-sm font-medium'>
          {connected ? '容器已连接' : '容器未连接（等待 llm-forwarder 上线）'}
        </span>
        {container?.host && (
          <span className='text-muted-foreground text-xs'>
            host={container.host}
            {aliveSec != null && ` · 本次会话 ${formatUptime(aliveSec)}`}
          </span>
        )}
      </div>

      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
        <Stat
          label='负载 (1/5/15m)'
          value={metrics ? metrics.load.map((x) => x.toFixed(2)).join(' / ') : '-'}
          hint='宿主机'
        />
        <Stat
          label={cgLimit ? '内存（容器）' : '内存'}
          value={metrics ? formatBytes(memUsed) : '-'}
          hint={memHint}
        />
        <Stat
          label='磁盘 /app'
          value={metrics?.disk?.total ? formatBytes(metrics.disk.used) : '-'}
          hint={
            metrics?.disk?.total
              ? `共 ${formatBytes(metrics.disk.total)} · ${diskPct.toFixed(0)}%`
              : undefined
          }
        />
        <Stat
          label='opencode 进程'
          value={metrics ? String(metrics.opencode_procs) : '-'}
          hint={aliveSec != null ? `容器存活 ${formatUptime(aliveSec)}` : undefined}
        />
      </div>
    </div>
  )
}
