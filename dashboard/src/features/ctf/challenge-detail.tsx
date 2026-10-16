import { useCtfStore } from './store'
import { LlmFeed } from './llm-feed'
import { statusClass, formatTime } from './helpers'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

function Blob({ text, empty }: { text?: string; empty: string }) {
  if (!text) return <div className='text-muted-foreground p-6 text-center text-sm'>{empty}</div>
  return (
    <ScrollArea className='h-[60vh]'>
      <pre className='p-3 pr-4 font-mono text-xs whitespace-pre-wrap'>{text}</pre>
    </ScrollArea>
  )
}

export function ChallengeDetail({ challengeId }: { challengeId: number }) {
  const scoreboard = useCtfStore((s) => s.scoreboard)
  const llm = useCtfStore((s) => s.llm)
  const notes = useCtfStore((s) => s.notes)
  const logs = useCtfStore((s) => s.logs)
  const workers = useCtfStore((s) => s.workers)

  const row = scoreboard.find((r) => r.id === String(challengeId))
  const events = llm.filter((e) => e.challenge_id === challengeId)
  const worker = workers.find((w) => w.id === challengeId)

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-3'>
        <h2 className='text-lg font-semibold'>
          #{challengeId} {row?.title ?? ''}
        </h2>
        {row?.status && (
          <Badge variant='outline' className={cn('font-mono text-[10px]', statusClass(row.status))}>
            {row.status}
          </Badge>
        )}
        {worker && (
          <span className='text-muted-foreground text-xs'>
            worker pid {worker.pid ?? '-'} · {worker.alive ? 'running' : 'dead'}
          </span>
        )}
      </div>

      <Tabs defaultValue='llm'>
        <TabsList>
          <TabsTrigger value='llm'>AI 请求 ({events.length})</TabsTrigger>
          <TabsTrigger value='notes'>笔记</TabsTrigger>
          <TabsTrigger value='log'>run.log</TabsTrigger>
          <TabsTrigger value='meta'>题目信息</TabsTrigger>
        </TabsList>

        <TabsContent value='llm'>
          <Card>
            <CardContent className='pt-6'>
              <LlmFeed events={events} empty='该题暂无 AI 请求' />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value='notes'>
          <Card>
            <CardHeader className='pb-3'>
              <CardTitle className='text-base'>work/{challengeId}/notes.md</CardTitle>
            </CardHeader>
            <CardContent>
              <Blob text={notes[challengeId]} empty='还没有笔记（等 worker 落盘）' />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value='log'>
          <Card>
            <CardHeader className='pb-3'>
              <CardTitle className='text-base'>work/{challengeId}/run.log</CardTitle>
            </CardHeader>
            <CardContent>
              <Blob text={logs[challengeId]} empty='暂无日志' />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value='meta'>
          <Card>
            <CardContent className='grid gap-2 pt-6 text-sm'>
              <div>分类：{row?.category || '-'}</div>
              <div>分值 / current_score：{row?.score || '-'} / {row?.current_score || '-'}</div>
              <div>Flag：{row?.flag || '-'}</div>
              <div>
                最近一次 AI 活动：
                {events.length ? formatTime(events[0].ts) : '-'}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
