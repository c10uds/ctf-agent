import type { Snapshot } from './types'

export async function fetchSnapshot(): Promise<Snapshot> {
  const res = await fetch('/api/snapshot')
  if (!res.ok) throw new Error(`snapshot ${res.status}`)
  return (await res.json()) as Snapshot
}

export async function fetchHistory(topic: string, limit = 200): Promise<unknown[]> {
  const res = await fetch(`/api/history?topic=${topic}&limit=${limit}`)
  if (!res.ok) throw new Error(`history ${res.status}`)
  return (await res.json()) as unknown[]
}

export async function sendChat(text: string): Promise<void> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(body || `chat ${res.status}`)
  }
}

export const STREAM_URL = '/api/stream'
