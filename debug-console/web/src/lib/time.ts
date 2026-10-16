/** 相对时间：x 秒/分钟/小时/天前；ts 为秒级 epoch */
export function formatRelative(ts: number | null | undefined): string {
  if (!ts) return '—'
  const diff = Math.max(0, Date.now() / 1000 - ts)
  if (diff < 5) return '刚刚'
  if (diff < 60) return `${Math.floor(diff)} 秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}

/** 绝对时间 HH:MM:SS */
export function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}
