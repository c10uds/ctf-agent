import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** 会话 id 短码：去掉 ses_ 前缀后取前 8 位 */
export function shortId(id: string): string {
  const s = id.startsWith('ses_') ? id.slice(4) : id
  return s.length > 8 ? `${s.slice(0, 8)}…` : s
}

/** 聊天请求 id：优先 crypto.randomUUID，非安全上下文退化为随机串 */
export function genReqId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
