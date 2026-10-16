export type PageKey = 'overview' | 'activities' | 'chat' | 'models'

export interface Challenge {
  id: number
  name: string
  category: string
  score: number
  current_score: number
  status: string // TODO/ANALYZING/LOCAL_READY/ATTACKING/SOLVED/BLOCKED/STUCK/SKIP
}

export interface Sliver {
  session_id: string
  challenge_id: number | null
  status: string // active / idle / finished
  title: string
  last_activity: number
}

export interface MasterInfo {
  session_id: string
  status: string
  last_activity: number
}

export interface ModelState {
  current: string | null
  pending: string | null
}

export interface Snapshot {
  master: MasterInfo | null
  challenges: Challenge[]
  slivers: Sliver[]
  scoreboard_md: string
  environments_md: string
  requests_md: string
  model: ModelState
}

export interface ActivityEntry {
  id: string
  ts: number
  kind: string // tool / text / reasoning / user
  tool: string | null
  title: string
  preview: string
}

export interface AgentStatus {
  agent_connected: boolean
  agent_hostname: string | null
  last_seen: number | null
}

export interface ChatMessage {
  req_id: string
  text: string
  ts: number
  from: 'user' | 'agent'
}

export interface PendingChat {
  req_id: string
  text: string
  ts: number
}

/** server → 浏览器 消息（见 CONTRACT.md） */
export type ServerMessage =
  | ({ type: 'status' } & AgentStatus)
  | { type: 'snapshot'; payload: Snapshot }
  | { type: 'activity'; session_id: string; challenge_id: number | null; entries: ActivityEntry[] }
  | { type: 'chat_reply'; req_id: string; text: string; ts: number }
  | ({ type: 'model_state' } & ModelState)
  | { type: 'error'; message: string }
