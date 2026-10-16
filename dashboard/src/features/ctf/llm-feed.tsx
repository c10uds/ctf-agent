import { useState } from 'react'
import type { LlmEvent } from './types'
import { agentClass, formatDuration, formatTime } from './helpers'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

function Row({ e }: { e: LlmEvent }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className='hover:bg-muted/40 cursor-pointer rounded-md border px-3 py-2'
      onClick={() => setOpen((v) => !v)}
    >
      <div className='flex flex-wrap items-center gap-2 text-xs'>
        <Badge variant='outline' className={cn('font-mono', agentClass(e.agent))}>
          {e.agent ?? 'unknown'}
        </Badge>
        {e.challenge_id != null && (
          <Badge variant='outline' className='font-mono'>
            #{e.challenge_id}
          </Badge>
        )}
        <span className='text-muted-foreground'>{formatTime(e.ts)}</span>
        <span className='text-muted-foreground truncate'>{e.model ?? ''}</span>
        {e.dur != null && <span className='text-muted-foreground'>耗时 {formatDuration(e.dur)}</span>}
        {e.tokens != null && <span className='text-muted-foreground'>tokens {e.tokens}</span>}
        {e.status != null && e.status !== 200 && (
          <span className='text-rose-500'>HTTP {e.status}</span>
        )}
        {e.status == null && <span className='text-amber-500'>进行中…</span>}
      </div>
      <div className={cn('text-muted-foreground mt-1 text-xs', !open && 'truncate')}>
        {e.error ? (
          <span className='text-rose-500'>{e.error}</span>
        ) : (
          <>→ {e.preview || '（无预览）'}</>
        )}
      </div>
      {e.resp_preview && (
        <div className={cn('text-muted-foreground mt-0.5 text-xs', !open && 'truncate')}>
          ← {e.resp_preview}
        </div>
      )}
    </div>
  )
}

export function LlmFeed({
  events,
  empty = '暂无 AI 请求',
}: {
  events: LlmEvent[]
  empty?: string
}) {
  if (!events.length) {
    return <div className='text-muted-foreground p-6 text-center text-sm'>{empty}</div>
  }
  return (
    <ScrollArea className='h-[60vh]'>
      <div className='space-y-2 pr-3'>
        {events.map((e) => (
          <Row key={e.id} e={e} />
        ))}
      </div>
    </ScrollArea>
  )
}
