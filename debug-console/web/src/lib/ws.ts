import { store } from './store'
import type { ServerMessage } from './types'

type Sendable = Record<string, unknown>

/**
 * 浏览器 → 本地 server 的 WS /ui 客户端。
 * 断线自动重连：2s 起步，指数退避，10s 封顶。
 */
class UiSocket {
  private ws: WebSocket | null = null
  private attempt = 0
  private timer: number | null = null

  connect() {
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return
    }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ui`)
    this.ws = ws

    ws.onopen = () => {
      if (this.ws !== ws) return
      this.attempt = 0
      store.setWsConnected(true)
    }
    ws.onmessage = (ev) => {
      try {
        store.handleMessage(JSON.parse(ev.data as string) as ServerMessage)
      } catch {
        // 忽略无法解析的消息
      }
    }
    ws.onclose = () => {
      if (this.ws !== ws) return
      store.setWsConnected(false)
      this.scheduleReconnect()
    }
    ws.onerror = () => {
      ws.close()
    }
  }

  private scheduleReconnect() {
    if (this.timer !== null) return
    const delay = Math.min(10000, 2000 * 2 ** this.attempt)
    this.attempt += 1
    this.timer = window.setTimeout(() => {
      this.timer = null
      this.connect()
    }, delay)
  }

  /** 连接未就绪时返回 false，由调用方决定提示或禁用 */
  send(msg: Sendable): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
      return true
    }
    return false
  }
}

export const socket = new UiSocket()
