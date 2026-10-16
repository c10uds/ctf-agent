import { useEffect, useState } from 'react'

/** 每 intervalMs 触发一次重渲染，用于刷新相对时间显示 */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(t)
  }, [intervalMs])
  return now
}
