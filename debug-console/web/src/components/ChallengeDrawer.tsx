import { ArrowRight, Clock, X } from 'lucide-react'
import type { Challenge, Sliver } from '../lib/types'
import { useNow } from '../lib/useNow'
import { formatRelative } from '../lib/time'
import { shortId } from '../lib/utils'
import { categoryVariant, challengeStatusVariant, sliverStatusVariant } from '../lib/badges'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { ScrollArea } from './ui/scroll-area'
import { Separator } from './ui/separator'

interface ChallengeDrawerProps {
  challenge: Challenge | null
  slivers: Sliver[]
  onClose: () => void
  onOpenActivities: (sessionId: string) => void
}

/** 题目详情抽屉：题目信息 + 该题全部 sliver 会话 */
export function ChallengeDrawer({ challenge, slivers, onClose, onOpenActivities }: ChallengeDrawerProps) {
  useNow(1000)
  if (!challenge) return null
  const related = slivers.filter((s) => s.challenge_id === challenge.id)
  return (
    <div className="fixed inset-0 z-40">
      <div className="animate-fade-in absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="animate-slide-in-right absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-white shadow-2xl">
        <div className="flex items-start justify-between p-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm text-slate-400">#{challenge.id}</span>
              <Badge variant={categoryVariant(challenge.category)}>{challenge.category}</Badge>
              <Badge variant={challengeStatusVariant(challenge.status)}>{challenge.status}</Badge>
            </div>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">{challenge.name}</h2>
            <p className="mt-1 text-sm text-slate-500">
              分值 {challenge.score} · 当前可得 {challenge.current_score}
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="关闭">
            <X />
          </Button>
        </div>
        <Separator />
        <ScrollArea className="flex-1 p-5">
          <h3 className="text-sm font-medium text-slate-500">Sliver 会话（{related.length}）</h3>
          {related.length === 0 && (
            <p className="mt-3 text-sm text-slate-400">该题暂无 sliver 会话。</p>
          )}
          <div className="mt-3 space-y-3">
            {related.map((s) => (
              <div key={s.session_id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-slate-500" title={s.session_id}>
                    {shortId(s.session_id)}
                  </span>
                  <Badge variant={sliverStatusVariant(s.status)}>{s.status}</Badge>
                </div>
                <p className="mt-1.5 line-clamp-2 text-sm text-slate-700">
                  {s.title || '（无标题）'}
                </p>
                <div className="mt-2 flex items-center justify-between">
                  <span className="flex items-center gap-1 text-xs text-slate-400">
                    <Clock className="h-3 w-3" />
                    {formatRelative(s.last_activity)}
                  </span>
                  <Button size="sm" variant="outline" onClick={() => onOpenActivities(s.session_id)}>
                    查看活动
                    <ArrowRight />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
