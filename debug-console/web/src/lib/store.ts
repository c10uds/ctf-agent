import { useSyncExternalStore } from 'react'
import type {
  ActivityEntry,
  AgentStatus,
  ChatMessage,
  ModelState,
  PendingChat,
  ServerMessage,
  Snapshot,
} from './types'

export interface AppState {
  /** 浏览器 ↔ 本地 server 的 WS 是否连通 */
  wsConnected: boolean
  /** server ↔ 容器 agent 状态（status 消息） */
  agent: AgentStatus
  snapshot: Snapshot | null
  model: ModelState
  /** session_id -> 活动记录（按 ts 升序，按 id 去重，最多保留 2000 条） */
  activities: Record<string, ActivityEntry[]>
  chat: ChatMessage[]
  pendingChats: PendingChat[]
  lastError: { message: string; ts: number } | null
}

const initialState: AppState = {
  wsConnected: false,
  agent: { agent_connected: false, agent_hostname: null, last_seen: null },
  snapshot: null,
  model: { current: null, pending: null },
  activities: {},
  chat: [],
  pendingChats: [],
  lastError: null,
}

const MAX_ACTIVITIES = 2000

class Store {
  private state: AppState = initialState
  private listeners = new Set<() => void>()

  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => {
      this.listeners.delete(fn)
    }
  }

  getState = () => this.state

  private set(partial: Partial<AppState>) {
    this.state = { ...this.state, ...partial }
    this.listeners.forEach((fn) => fn())
  }

  setWsConnected(v: boolean) {
    this.set({ wsConnected: v })
  }

  handleMessage(msg: ServerMessage) {
    switch (msg.type) {
      case 'status':
        this.set({
          agent: {
            agent_connected: msg.agent_connected,
            agent_hostname: msg.agent_hostname,
            last_seen: msg.last_seen,
          },
        })
        break
      case 'snapshot':
        this.set({ snapshot: msg.payload, model: msg.payload.model ?? this.state.model })
        break
      case 'activity': {
        const prev = this.state.activities[msg.session_id] ?? []
        const seen = new Set(prev.map((e) => e.id))
        const merged = [...prev]
        for (const e of msg.entries) {
          if (e.id && !seen.has(e.id)) {
            seen.add(e.id)
            merged.push(e)
          }
        }
        merged.sort((a, b) => a.ts - b.ts)
        this.set({
          activities: {
            ...this.state.activities,
            [msg.session_id]: merged.slice(-MAX_ACTIVITIES),
          },
        })
        break
      }
      case 'chat_reply':
        this.set({
          pendingChats: this.state.pendingChats.filter((p) => p.req_id !== msg.req_id),
          chat: [
            ...this.state.chat,
            { req_id: msg.req_id, text: msg.text, ts: msg.ts, from: 'agent' },
          ],
        })
        break
      case 'model_state':
        this.set({ model: { current: msg.current ?? null, pending: msg.pending ?? null } })
        break
      case 'error':
        this.set({ lastError: { message: msg.message, ts: Date.now() / 1000 } })
        break
    }
  }

  /** 发送成功后调用：本地立即上屏用户气泡 + 登记等待中的回复 */
  sendChat(reqId: string, text: string) {
    this.set({
      chat: [...this.state.chat, { req_id: reqId, text, ts: Date.now() / 1000, from: 'user' }],
      pendingChats: [...this.state.pendingChats, { req_id: reqId, text, ts: Date.now() / 1000 }],
    })
  }

  dismissError() {
    this.set({ lastError: null })
  }
}

export const store = new Store()

export function useAppState(): AppState {
  return useSyncExternalStore(store.subscribe, store.getState)
}
