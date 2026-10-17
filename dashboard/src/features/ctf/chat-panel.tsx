import { useEffect, useRef, useState } from 'react'
import { sendChat } from './api'
import { useCtfStore } from './store'
import { formatTime } from './helpers'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

export function ChatPanel() {
  const chat = useCtfStore((s) => s.chat)
  const connected = useCtfStore((s) => s.connected)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  // 最新消息在最上面：新消息到达时回到顶部
  useEffect(() => {
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }, [chat.length])

  const send = async () => {
    const value = text.trim()
    if (!value || busy) return
    setError('')
    setBusy(true)
    try {
      await sendChat(value)
      setText('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className='flex h-[75vh] flex-col'>
      <CardHeader className='pb-3'>
        <CardTitle className='text-base'>与 CTF-Customer 对话</CardTitle>
        <p className='text-muted-foreground text-xs'>
          一切操作交给 customer：它只写 state/REQUESTS.md，由容器内 Master 执行。
          {!connected && ' 容器未连接，发送会失败。'}
        </p>
      </CardHeader>
      <CardContent className='flex min-h-0 flex-1 flex-col gap-3'>
        <div ref={listRef} className='min-h-0 flex-1 space-y-3 overflow-y-auto pr-1'>
          {chat.length === 0 && (
            <div className='text-muted-foreground py-10 text-center text-sm'>
              还没有对话。试试「现在进度如何」。
            </div>
          )}
          {[...chat].reverse().map((m) => (
            <div
              key={m.id}
              className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}
            >
              <div
                className={cn(
                  'max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap',
                  m.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                )}
              >
                {m.text || (m.done ? '（空回复）' : '…')}
                {!m.done && m.role === 'assistant' && (
                  <span className='text-muted-foreground ml-1 animate-pulse'>▌</span>
                )}
                {m.error && <div className='text-rose-500 mt-1 text-xs'>{m.error}</div>}
                <div className='text-muted-foreground mt-1 text-[10px] opacity-70'>
                  {formatTime(m.ts)}
                </div>
              </div>
            </div>
          ))}
        </div>
        {error && <div className='text-rose-500 text-xs'>{error}</div>}
        <div className='flex gap-2'>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            placeholder='例如：现在进度如何 / 优先做 web 第 8 题 / 授权查看第 12 题提示'
            className='min-h-[44px] resize-none'
            rows={2}
          />
          <Button onClick={() => void send()} disabled={busy || !text.trim()}>
            {busy ? '发送中…' : '发送'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
