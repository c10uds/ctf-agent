import { useEffect } from 'react'
import { STREAM_URL } from './api'
import { useCtfStore } from './store'
import type { StreamEvent } from './types'

const TOPICS = [
  'hello',
  'metrics',
  'proc',
  'env',
  'scoreboard',
  'fs',
  'llm_req',
  'llm_resp',
  'chat',
]

/**
 * 与后端建立一条 SSE 长连接，把事件实时灌进 store。
 * 推流而非轮询：EventSource 断线会自动重连，重连后后端会补发 snapshot + replay。
 */
export function LiveBridge() {
  const applyEvent = useCtfStore((s) => s.applyEvent)
  const applySnapshot = useCtfStore((s) => s.applySnapshot)
  const setConnected = useCtfStore((s) => s.setConnected)

  useEffect(() => {
    const es = new EventSource(STREAM_URL)
    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)

    const feed = (ev: MessageEvent) => {
      try {
        applyEvent(JSON.parse(ev.data) as StreamEvent)
      } catch {
        /* 忽略坏帧 */
      }
    }
    const feeds = TOPICS.map((t) => {
      const handler = feed as EventListener
      es.addEventListener(t, handler)
      return () => es.removeEventListener(t, handler)
    })

    const onSnapshot = (ev: MessageEvent) => {
      try {
        applySnapshot(JSON.parse(ev.data))
      } catch {
        /* 忽略 */
      }
    }
    es.addEventListener('snapshot', onSnapshot as EventListener)

    return () => {
      feeds.forEach((off) => off())
      es.removeEventListener('snapshot', onSnapshot as EventListener)
      es.close()
    }
  }, [applyEvent, applySnapshot, setConnected])

  return null
}
