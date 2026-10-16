import { useEffect, useRef, useState } from 'react'
import { Bot, Send, User } from 'lucide-react'
import { store, useAppState } from '../lib/store'
import { socket } from '../lib/ws'
import { genReqId, cn } from '../lib/utils'
import { formatTime } from '../lib/time'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { ScrollArea } from '../components/ui/scroll-area'

export function ChatPage() {
  const state = useAppState()
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const ready = state.wsConnected && state.agent.agent_connected

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [state.chat.length, state.pendingChats.length])

  const send = () => {
    const text = input.trim()
    if (!text || !ready) return
    const reqId = genReqId()
    if (!socket.send({ type: 'chat', req_id: reqId, text })) return
    store.sendChat(reqId, text)
    setInput('')
  }

  return (
    <div className="flex h-full flex-col p-6">
      <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-slate-200 bg-white shadow-sm">
        <ScrollArea ref={scrollRef} className="flex-1 p-4">
          {state.chat.length === 0 && state.pendingChats.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              暂无消息，试试问：「现在进度如何」
            </div>
          ) : (
            <div className="space-y-4">
              {state.chat.map((m, i) => (
                <div
                  key={`${m.req_id}-${m.from}-${i}`}
                  className={cn('flex gap-2.5', m.from === 'user' && 'flex-row-reverse')}
                >
                  <div
                    className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                      m.from === 'user'
                        ? 'bg-slate-900 text-white'
                        : 'border border-slate-200 bg-slate-50 text-slate-500',
                    )}
                  >
                    {m.from === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                  </div>
                  <div
                    className={cn(
                      'max-w-[70%] rounded-2xl px-4 py-2.5 text-sm',
                      m.from === 'user'
                        ? 'rounded-tr-sm bg-slate-900 text-white'
                        : 'rounded-tl-sm border border-slate-200 bg-slate-50 text-slate-800',
                    )}
                  >
                    <p className="whitespace-pre-wrap break-all">{m.text}</p>
                    <p className="mt-1 text-right text-[10px] text-slate-400">
                      {formatTime(m.ts)}
                    </p>
                  </div>
                </div>
              ))}
              {state.pendingChats.length > 0 && (
                <div className="flex gap-2.5">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-500">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-slate-200 bg-slate-50 px-4 py-3">
                    <span className="text-xs text-slate-400">对方正在输入</span>
                    <span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" />
                    <span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" />
                    <span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" />
                  </div>
                </div>
              )}
            </div>
          )}
        </ScrollArea>

        <div className="border-t border-slate-200 p-4">
          {!ready && (
            <p className="mb-2 text-xs text-amber-600">
              容器 Agent 未连接，暂时无法发送消息。请确认容器已启动且已回连控制台。
            </p>
          )}
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              send()
            }}
          >
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={ready ? '向 CTF-Customer 提问，如：现在进度如何' : '容器未连接，输入已禁用'}
              disabled={!ready}
            />
            <Button type="submit" disabled={!ready || !input.trim()}>
              <Send />
              发送
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}
