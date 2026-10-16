import { create } from 'zustand'
import type {
  ChatMessage,
  ContainerInfo,
  EnvRequest,
  EnvRow,
  LlmEvent,
  Metrics,
  ScoreRow,
  Snapshot,
  StreamEvent,
  WorkerProc,
} from './types'

const MAX_LLM = 500
const MAX_CHAT = 200

interface CtfState {
  connected: boolean
  container: ContainerInfo | null
  metrics: Metrics | null
  workers: WorkerProc[]
  scoreboard: ScoreRow[]
  environments: EnvRow[]
  requests: EnvRequest[]
  llm: LlmEvent[]
  chat: ChatMessage[]
  notes: Record<number, string>
  logs: Record<number, string>
  applySnapshot: (s: Snapshot) => void
  applyEvent: (e: StreamEvent) => void
  setConnected: (v: boolean) => void
  upsertChat: (m: Partial<ChatMessage> & { id: number }) => void
}

function num(v: unknown): number | undefined {
  return typeof v === 'number' ? v : undefined
}

export const useCtfStore = create<CtfState>((set) => ({
  connected: false,
  container: null,
  metrics: null,
  workers: [],
  scoreboard: [],
  environments: [],
  requests: [],
  llm: [],
  chat: [],
  notes: {},
  logs: {},

  setConnected: (v) => set({ connected: v }),

  applySnapshot: (s) =>
    set((state) => ({
      container: s.container ?? state.container,
      metrics: s.metrics ?? state.metrics,
      workers: s.proc?.workers ?? Object.values(s.workers ?? {}),
      scoreboard: s.scoreboard?.length ? s.scoreboard : state.scoreboard,
      environments: s.environments?.length ? s.environments : state.environments,
      requests: s.requests ?? state.requests,
      llm: mergeLlm(s.llm ?? [], state.llm),
      chat: mergeChat(s.chat ?? [], state.chat),
    })),

  applyEvent: (e) =>
    set((state) => {
      const d = e.data as Record<string, unknown>
      switch (e.topic) {
        case 'hello':
          return { container: d as ContainerInfo, connected: d.connected !== false }
        case 'metrics':
          return { metrics: d as unknown as Metrics }
        case 'proc':
          return { workers: (d.workers as WorkerProc[]) ?? [] }
        case 'env':
          return {
            environments: (d.environments as EnvRow[]) ?? [],
            requests: (d.requests as EnvRequest[]) ?? [],
          }
        case 'scoreboard':
          return { scoreboard: (d.rows as ScoreRow[]) ?? [] }
        case 'fs': {
          const kind = d.kind as string
          const cid = num(d.challenge_id)
          const tail = typeof d.tail === 'string' ? d.tail : ''
          if (cid == null) return {}
          if (kind === 'notes') return { notes: { ...state.notes, [cid]: tail } }
          if (kind === 'log') return { logs: { ...state.logs, [cid]: tail } }
          return {}
        }
        case 'llm_req':
          return { llm: mergeLlm([d as unknown as LlmEvent], state.llm) }
        case 'llm_resp':
          return { llm: mergeLlm([d as unknown as LlmEvent], state.llm) }
        case 'chat': {
          const msg = d as unknown as ChatMessage
          return { chat: upsert(state.chat, msg) }
        }
        default:
          return {}
      }
    }),

  upsertChat: (m) => set((state) => ({ chat: upsert(state.chat, m as ChatMessage) })),
}))

function mergeLlm(incoming: LlmEvent[], existing: LlmEvent[]): LlmEvent[] {
  if (!incoming.length) return existing
  const map = new Map<number, LlmEvent>()
  for (const e of existing) map.set(e.id, e)
  for (const e of incoming) {
    if (e.id == null) continue
    const prev = map.get(e.id)
    map.set(e.id, { ...prev, ...stripUndefined(e), id: e.id, ts: e.ts ?? prev?.ts })
  }
  return Array.from(map.values())
    .sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0))
    .slice(0, MAX_LLM)
}

function mergeChat(incoming: ChatMessage[], existing: ChatMessage[]): ChatMessage[] {
  let out = existing
  for (const m of incoming) out = upsert(out, m)
  return out.slice(-MAX_CHAT)
}

function upsert(list: ChatMessage[], msg: Partial<ChatMessage> & { id: number }): ChatMessage[] {
  const idx = list.findIndex((m) => m.id === msg.id)
  if (idx === -1) {
    const created: ChatMessage = {
      id: msg.id,
      role: msg.role ?? 'assistant',
      text: msg.text ?? msg.delta ?? '',
      done: msg.done,
      exit_code: msg.exit_code,
      error: msg.error,
      ts: msg.ts,
    }
    return [...list, created].slice(-MAX_CHAT)
  }
  const next = [...list]
  const prev = next[idx]
  const text = msg.delta ? (prev.text ?? '') + msg.delta : msg.text ?? prev.text
  next[idx] = { ...prev, ...stripUndefined(msg), text }
  return next
}

function stripUndefined<T extends object>(obj: T): Partial<T> {
  const out: Partial<T> = {}
  for (const [k, v] of Object.entries(obj)) {
    if (v !== undefined) out[k as keyof T] = v as T[keyof T]
  }
  return out
}
