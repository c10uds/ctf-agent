export type AgentName = 'master' | 'worker' | 'customer' | 'unknown' | 'direct'

export interface LlmEvent {
  id: number
  agent?: AgentName
  challenge_id?: number | null
  model?: string
  orig_model?: string
  stream?: boolean
  preview?: string
  resp_preview?: string
  tokens?: number
  prompt_tokens?: number
  completion_tokens?: number
  dur?: number
  status?: number
  error?: string
  ts?: number
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text?: string
  delta?: string
  done?: boolean
  exit_code?: number
  error?: string
  ts?: number
}

export interface Metrics {
  load: number[]
  mem_total: number
  mem_used: number
  disk: { total: number; used: number; free: number }
  uptime: number
  opencode_procs: number
  ts: number
}

export interface WorkerProc {
  id: number
  pid: number | null
  alive: boolean
  rss?: number
  cpu_ticks?: number
  started_at?: number
}

export interface ContainerInfo {
  host?: string
  pid?: number
  app_dir?: string
  uptime?: number
  connected?: boolean
}

export interface ScoreRow {
  id: string
  title: string
  category: string
  score: string
  current_score: string
  status: string
  flag: string
}

export interface EnvRow {
  id: string
  entry: string
  since: string
  usage: string
}

export interface EnvRequest {
  file: string
  challenge_id: string
  preempted?: boolean
  type?: string
  category?: string
  requested_at?: string
  preempted_at?: string
}

export interface FileState {
  mtime?: number
  size?: number
  challenge_id?: number | null
  kind?: string
  tail?: string
  deleted?: boolean
}

export interface FsEvent {
  path: string
  rel: string
  kind: 'notes' | 'log' | 'state' | 'req'
  challenge_id?: number | null
  mtime?: number
  size?: number
  tail?: string
  deleted?: boolean
}

export interface Snapshot {
  container: ContainerInfo | null
  metrics: Metrics | null
  proc: { workers: WorkerProc[] } | null
  workers: Record<string, WorkerProc>
  files: Record<string, FileState>
  scoreboard: ScoreRow[]
  llm: LlmEvent[]
  chat: ChatMessage[]
  environments: EnvRow[]
  requests: EnvRequest[]
}

export interface StreamEvent {
  topic: string
  ts?: number
  data: Record<string, unknown>
}
