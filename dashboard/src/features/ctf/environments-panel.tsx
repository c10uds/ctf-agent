import { useCtfStore } from './store'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

export function EnvironmentsPanel() {
  const environments = useCtfStore((s) => s.environments)
  const requests = useCtfStore((s) => s.requests)

  return (
    <div className='grid gap-4 lg:grid-cols-2'>
      <Card>
        <CardHeader className='pb-3'>
          <CardTitle className='text-base'>当前动态环境</CardTitle>
        </CardHeader>
        <CardContent className='space-y-2'>
          {environments.length === 0 && (
            <div className='text-muted-foreground text-sm'>当前无开启的环境</div>
          )}
          {environments.map((e) => (
            <div key={e.id} className='rounded-md border px-3 py-2 text-sm'>
              <div className='flex items-center gap-2'>
                <Badge variant='outline' className='font-mono'>
                  #{e.id}
                </Badge>
                <span className='text-muted-foreground text-xs'>{e.since}</span>
              </div>
              <div className='mt-1 font-mono text-xs break-all'>{e.entry || '-'}</div>
              {e.usage && <div className='text-muted-foreground text-xs'>用途：{e.usage}</div>}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className='pb-3'>
          <CardTitle className='text-base'>环境申请队列（state/env-requests/）</CardTitle>
        </CardHeader>
        <CardContent className='space-y-2'>
          {requests.length === 0 && (
            <div className='text-muted-foreground text-sm'>队列为空</div>
          )}
          {requests.map((r) => (
            <div key={r.file} className='rounded-md border px-3 py-2 text-sm'>
              <div className='flex flex-wrap items-center gap-2'>
                <Badge variant='outline' className='font-mono'>
                  #{r.challenge_id}
                </Badge>
                {r.category && <span className='text-xs'>{r.category}</span>}
                {r.type && <span className='text-muted-foreground text-xs'>{r.type}</span>}
                {r.preempted && (
                  <Badge variant='outline' className='border-rose-500/30 text-[10px] text-rose-500'>
                    抢占恢复
                  </Badge>
                )}
              </div>
              <Separator className='my-2' />
              <div className='text-muted-foreground text-xs'>
                requested_at: {r.requested_at || '-'}
                {r.preempted_at ? ` · preempted_at: ${r.preempted_at}` : ''}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
