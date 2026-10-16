import { useEffect, useMemo, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useAppState } from '../lib/store'
import { socket } from '../lib/ws'
import { formatTime } from '../lib/time'
import { shortId } from '../lib/utils'
import { activityKindLabel, activityKindVariant } from '../lib/badges'
import type { ActivityEntry } from '../lib/types'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Card, CardContent } from '../components/ui/card'
import { Dialog } from '../components/ui/dialog'
import { ScrollArea } from '../components/ui/scroll-area'
import { Select } from '../components/ui/select'
import { Switch } from '../components/ui/switch'

interface ActivitiesPageProps {
  sessionId: string | null
  onSessionChange: (id: string) => void
}

function ActivityRow({ entry, onClick }: { entry: ActivityEntry; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="block w-full rounded-lg border border-slate-200 bg-white p-3 text-left transition hover:border-slate-300 hover:shadow-sm"
    >
      <div className="flex items-center gap-2">
        <span className="shrink-0 font-mono text-xs text-slate-400">{formatTime(entry.ts)}</span>
        <Badge variant={activityKindVariant(entry.kind)}>{activityKindLabel(entry.kind)}</Badge>
        <span className="truncate text-sm font-medium text-slate-700">
          {entry.kind === 'tool' ? (entry.tool ?? entry.title) : entry.title}
        </span>
      </div>
      <pre className="mt-2 line-clamp-3 whitespace-pre-wrap break-all font-mono text-xs text-slate-500">
        {entry.preview}
      </pre>
    </button>
  )
}

export function ActivitiesPage({ sessionId, onSessionChange }: ActivitiesPageProps) {
  const state = useAppState()
  const [autoScroll, setAutoScroll] = useState(true)
  const [detail, setDetail] = useState<ActivityEntry | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const { snapshot, wsConnected } = state

  // 下拉选项：master + 全部 sliver
  const options = useMemo(() => {
    const list: { id: string; label: string }[] = []
    if (snapshot?.master) {
      list.push({
        id: snapshot.master.session_id,
        label: `Master · ${shortId(snapshot.master.session_id)}`,
      })
    }
    const nameOf = new Map((snapshot?.challenges ?? []).map((c) => [c.id, c.name]))
    for (const s of snapshot?.slivers ?? []) {
      const prefix = s.challenge_id != null ? `#${s.challenge_id} ${nameOf.get(s.challenge_id) ?? ''}` : '未关联题目'
      list.push({ id: s.session_id, label: `${prefix} · ${shortId(s.session_id)}` })
    }
    return list
  }, [snapshot])

  // 未选择时默认选中 master 会话
  useEffect(() => {
    if (!sessionId && snapshot?.master) onSessionChange(snapshot.master.session_id)
  }, [sessionId, snapshot, onSessionChange])

  // 进入会话 / 重连后拉取全量活动；此后该会话的 activity 推送实时追加
  useEffect(() => {
    if (sessionId && wsConnected) {
      socket.send({ type: 'get_activities', session_id: sessionId })
    }
  }, [sessionId, wsConnected])

  const entries = sessionId ? (state.activities[sessionId] ?? []) : []

  useEffect(() => {
    if (autoScroll) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [entries.length, autoScroll])

  const refresh = () => {
    if (sessionId) socket.send({ type: 'get_activities', session_id: sessionId })
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 p-4">
          <div className="min-w-64 flex-1">
            <Select value={sessionId ?? ''} onChange={(e) => onSessionChange(e.target.value)}>
              <option value="" disabled>
                选择会话…
              </option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
              {sessionId && !options.some((o) => o.id === sessionId) && (
                <option value={sessionId}>{sessionId}</option>
              )}
            </Select>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <Switch checked={autoScroll} onCheckedChange={setAutoScroll} />
            自动滚动到底部
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={refresh}
            disabled={!sessionId || !wsConnected}
          >
            <RefreshCw />
            刷新
          </Button>
          <span className="text-xs text-slate-400">{entries.length} 条记录</span>
        </CardContent>
      </Card>

      <Card className="min-h-0 flex-1 overflow-hidden">
        {!sessionId ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            请先选择一个会话
          </div>
        ) : entries.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            该会话暂无活动记录
          </div>
        ) : (
          <ScrollArea ref={scrollRef} className="h-full bg-slate-50 p-4">
            <div className="space-y-2">
              {entries.map((e) => (
                <ActivityRow key={e.id} entry={e} onClick={() => setDetail(e)} />
              ))}
            </div>
          </ScrollArea>
        )}
      </Card>

      <Dialog
        open={detail !== null}
        onClose={() => setDetail(null)}
        title={detail ? `${activityKindLabel(detail.kind)} · ${formatTime(detail.ts)}` : undefined}
        description={detail?.kind === 'tool' ? `工具：${detail.tool ?? detail.title}` : undefined}
      >
        {detail && (
          <>
            <ScrollArea className="max-h-80 rounded-md bg-slate-50 p-3">
              <pre className="whitespace-pre-wrap break-all font-mono text-xs text-slate-700">
                {detail.preview || '（空）'}
              </pre>
            </ScrollArea>
            <p className="mt-2 text-xs text-slate-400">
              preview 由服务端固定截取前 200 字符 · id: {detail.id}
            </p>
          </>
        )}
      </Dialog>
    </div>
  )
}
