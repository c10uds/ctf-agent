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

  const memPct = metrics && metrics.mem_total ? (metrics.mem_used / metrics.mem_total) * 100 : 0
  const diskPct =
    metrics && metrics.disk?.total ? (metrics.disk.used / metrics.disk.total) * 100 : 0

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
            host={container.host} · 容器运行 {formatUptime(container.uptime)}
          </span>
        )}
      </div>

      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
        <Stat
          label='负载 (1/5/15m)'
          value={metrics ? metrics.load.map((x) => x.toFixed(2)).join(' / ') : '-'}
        />
        <Stat
          label='内存'
          value={metrics ? `${formatBytes(metrics.mem_used)}` : '-'}
          hint={metrics ? `共 ${formatBytes(metrics.mem_total)} · ${memPct.toFixed(0)}%` : undefined}
        />
        <Stat
          label='磁盘 /app'
          value={metrics?.disk?.total ? formatBytes(metrics.disk.used) : '-'}
          hint={metrics?.disk?.total ? `共 ${formatBytes(metrics.disk.total)} · ${diskPct.toFixed(0)}%` : undefined}
        />
        <Stat
          label='opencode 进程'
          value={metrics ? String(metrics.opencode_procs) : '-'}
          hint={metrics ? `容器启动 ${formatUptime(metrics.uptime)}` : undefined}
        />
      </div>
    </div>
  )
}
