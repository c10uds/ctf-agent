import type { AgentName } from './types'

export function formatBytes(n?: number): string {
  if (!n && n !== 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatUptime(sec?: number): string {
  if (!sec) return '-'
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export function formatTime(ts?: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

export function formatDuration(sec?: number): string {
  if (sec == null) return '-'
  return sec >= 10 ? `${sec.toFixed(0)}s` : `${sec.toFixed(1)}s`
}

export function agentClass(agent?: AgentName): string {
  switch (agent) {
    case 'master':
      return 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30'
    case 'worker':
      return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
    case 'customer':
      return 'bg-violet-500/15 text-violet-600 dark:text-violet-400 border-violet-500/30'
    default:
      return 'bg-muted text-muted-foreground border-border'
  }
}

export function statusClass(status?: string): string {
  const s = (status ?? '').toUpperCase()
  if (s === 'SOLVED') return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
  if (s === 'ATTACKING') return 'bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30'
  if (s === 'LOCAL_READY' || s === 'ENV_QUEUED') return 'bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30'
  if (s === 'ANALYZING') return 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30'
  if (s === 'BLOCKED' || s === 'STUCK') return 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30'
  return 'bg-muted text-muted-foreground border-border'
}

export function statusOf(rows: { id: string; status: string }[], id?: number | string): string {
  if (id == null) return ''
  return rows.find((r) => String(r.id) === String(id))?.status ?? ''
}
