import { useEffect } from 'react'
import { fetchSnapshot, STREAM_URL } from './api'
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
    // 首屏不等 SSE：立刻拉一次快照，刷新后数据和流式通道并行加载
    const load = () => {
      fetchSnapshot()
        .then(applySnapshot)
        .catch(() => {
          /* 网关没起来时忽略，SSE 重连后会再拉 */
        })
    }
    load()

    const es = new EventSource(STREAM_URL)
    es.onopen = () => {
      setConnected(true)
      load() // 重连后补齐断线期间的状态
    }
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

    // 重连/刷新时后端会补发最近事件（{topic, ts, data}），同样灌进 store
    const onReplay = (ev: MessageEvent) => {
      try {
        applyEvent(JSON.parse(ev.data) as StreamEvent)
      } catch {
        /* 忽略 */
      }
    }
    es.addEventListener('replay', onReplay as EventListener)

    return () => {
      feeds.forEach((off) => off())
      es.removeEventListener('snapshot', onSnapshot as EventListener)
      es.removeEventListener('replay', onReplay as EventListener)
      es.close()
    }
  }, [applyEvent, applySnapshot, setConnected])

  return null
}
