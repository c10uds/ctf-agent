import { useState } from 'react'
import type { LlmEvent, LlmMessage } from './types'
import { agentClass, formatBytes, formatDuration, formatTime } from './helpers'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const ROLE_CLASS: Record<string, string> = {
  system: 'bg-slate-500/15 text-slate-600 dark:text-slate-300 border-slate-500/30',
  user: 'bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30',
  assistant: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  tool: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
}

const TOOLS_COLLAPSED = 10
const MSGS_COLLAPSED = 8

function MiniButton({
  children,
  onClick,
}: {
  children: React.ReactNode
  onClick: (ev: React.MouseEvent) => void
}) {
  return (
    <button
      className='text-muted-foreground hover:text-foreground border-border rounded border px-1.5 py-0.5 text-[10px]'
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <MiniButton
      onClick={(ev) => {
        ev.stopPropagation()
        navigator.clipboard?.writeText(text).then(
          () => {
            setDone(true)
            window.setTimeout(() => setDone(false), 1200)
          },
          () => undefined
        )
      }}
    >
      {done ? '已复制' : '复制'}
    </MiniButton>
  )
}

function Section({
  title,
  hint,
  copy,
  extra,
  children,
}: {
  title: string
  hint?: string
  copy?: string
  extra?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className='min-w-0 space-y-1'>
      <div className='text-muted-foreground flex items-center gap-2 text-[11px] font-medium'>
        <span>{title}</span>
        {hint && <span className='text-muted-foreground/70'>{hint}</span>}
        {extra}
        {copy && <CopyButton text={copy} />}
      </div>
      {children}
    </div>
  )
}

function Pre({ text, className }: { text: string; className?: string }) {
  return (
    <pre
      className={cn(
        'bg-muted/40 max-h-72 min-w-0 overflow-auto rounded-md p-2 font-mono text-[11px] leading-relaxed break-words whitespace-pre-wrap',
        className
      )}
    >
      {text}
    </pre>
  )
}

function MessageView({ m }: { m: LlmMessage }) {
  const [open, setOpen] = useState(false)
  const len = m.len ?? m.text.length
  return (
    <div className='min-w-0 rounded-md border'>
      <div
        className='hover:bg-muted/40 flex cursor-pointer items-center gap-2 px-2 py-1'
        onClick={() => setOpen((v) => !v)}
      >
        <Badge variant='outline' className={cn('shrink-0 font-mono', ROLE_CLASS[m.role] ?? '')}>
          {m.role}
        </Badge>
        <span className='text-muted-foreground shrink-0 font-mono'>{len} 字符</span>
        {m.truncated && <span className='shrink-0 text-amber-500'>已截断</span>}
        <span className='text-muted-foreground ml-auto shrink-0 text-[10px]'>
          {open ? '收起' : '展开'}
        </span>
      </div>
      {open ? (
        <Pre text={m.text} className='mx-2 mb-2 max-h-64' />
      ) : (
        <div className='text-muted-foreground truncate px-2 pb-1 text-[11px]'>
          {m.text.slice(0, 160)}
        </div>
      )}
    </div>
  )
}

function Kv({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className='flex min-w-0 gap-1 text-[11px]'>
      <span className='text-muted-foreground shrink-0'>{k}</span>
      <span className='min-w-0 font-mono break-all'>{v}</span>
    </div>
  )
}

function Detail({ e }: { e: LlmEvent }) {
  const [showThinking, setShowThinking] = useState(false)
  const [showAllTools, setShowAllTools] = useState(false)
  const [showAllMsgs, setShowAllMsgs] = useState(false)
  const params = e.params ?? {}
  const paramKeys = Object.keys(params)
  const tools = e.tools ?? []
  const msgs = e.messages ?? []
  const hasDetail = paramKeys.length > 0 || msgs.length > 0 || !!e.text || !!e.reasoning

  // 长列表默认只给最近的部分，避免一屏全是工具名/历史消息
  const shownTools = showAllTools ? tools : tools.slice(0, TOOLS_COLLAPSED)
  const shownMsgs =
    showAllMsgs || msgs.length <= MSGS_COLLAPSED
      ? msgs
      : [msgs[0], ...msgs.slice(-(MSGS_COLLAPSED - 1))]

  return (
    <div className='mt-2 min-w-0 space-y-3 border-t pt-2' onClick={(ev) => ev.stopPropagation()}>
      <div className='grid grid-cols-2 gap-x-4 gap-y-0.5 md:grid-cols-3'>
        <Kv k='模型' v={e.model ?? '-'} />
        {e.orig_model && e.orig_model !== e.model && <Kv k='原始模型' v={e.orig_model} />}
        <Kv k='路径' v={e.path ?? '- '} />
        <Kv k='流式' v={e.stream == null ? '-' : e.stream ? '是' : '否'} />
        <Kv k='状态' v={e.status ?? '进行中…'} />
        <Kv k='耗时' v={e.dur != null ? formatDuration(e.dur) : '-'} />
        <Kv k='tokens' v={e.tokens ?? '-'} />
        <Kv
          k='输入/输出'
          v={
            e.prompt_tokens != null || e.completion_tokens != null
              ? `${e.prompt_tokens ?? '?'} / ${e.completion_tokens ?? '?'}`
              : '-'
          }
        />
        <Kv k='结束原因' v={e.finish_reason ?? '-'} />
        <Kv k='请求体' v={e.body_len != null ? formatBytes(e.body_len) : '-'} />
        <Kv k='消息数' v={e.message_count ?? '-'} />
        <Kv k='工具数' v={e.tools?.length ?? '-'} />
      </div>

      {!hasDetail && (
        <div className='text-muted-foreground text-[11px]'>
          这条请求的详细内容已省略（面板只保留最近若干条的完整详情）。
        </div>
      )}

      {e.error && (
        <Section title='错误' copy={e.error}>
          <Pre text={e.error} className='text-rose-500' />
        </Section>
      )}

      {paramKeys.length > 0 && (
        <Section title='请求参数' copy={JSON.stringify(params, null, 2)}>
          <Pre text={JSON.stringify(params, null, 2)} className='max-h-40' />
        </Section>
      )}

      {tools.length > 0 && (
        <Section
          title={`可用工具（${tools.length}）`}
          copy={tools.join('\n')}
          extra={
            tools.length > TOOLS_COLLAPSED ? (
              <MiniButton onClick={() => setShowAllTools((v) => !v)}>
                {showAllTools ? '收起' : `展开全部 ${tools.length}`}
              </MiniButton>
            ) : undefined
          }
        >
          <div className='flex flex-wrap gap-1'>
            {shownTools.map((t) => (
              <Badge key={t} variant='outline' className='font-mono'>
                {t}
              </Badge>
            ))}
          </div>
        </Section>
      )}

      {msgs.length > 0 && (
        <Section
          title={`请求消息（${msgs.length}）`}
          hint={e.messages_trimmed ? `共 ${e.message_count} 条，已省略中间部分` : undefined}
          copy={msgs.map((m) => `### ${m.role} (${m.len ?? m.text.length})\n${m.text}`).join('\n\n')}
          extra={
            msgs.length > MSGS_COLLAPSED ? (
              <MiniButton onClick={() => setShowAllMsgs((v) => !v)}>
                {showAllMsgs ? '只看最近' : `展开全部 ${msgs.length}`}
              </MiniButton>
            ) : undefined
          }
        >
          <div className='min-w-0 space-y-1'>
            {!showAllMsgs && msgs.length > MSGS_COLLAPSED && (
              <div className='text-muted-foreground px-1 text-[10px]'>
                （省略了中间 {msgs.length - MSGS_COLLAPSED} 条）
              </div>
            )}
            {shownMsgs.map((m, i) => (
              <MessageView key={`${m.role}-${i}`} m={m} />
            ))}
          </div>
        </Section>
      )}

      <Section
        title='响应正文'
        hint={e.text_truncated ? '已截断' : undefined}
        copy={e.text ?? e.resp_preview}
      >
        {e.text ? (
          <Pre text={e.text} />
        ) : e.resp_preview ? (
          <Pre text={e.resp_preview} />
        ) : (
          <div className='text-muted-foreground text-[11px]'>等待响应…</div>
        )}
      </Section>

      {!!e.tool_calls?.length && (
        <Section title={`响应中的工具调用（${e.tool_calls.length}）`}>
          <div className='min-w-0 space-y-1'>
            {e.tool_calls.map((c, i) => (
              <div key={i} className='min-w-0 rounded-md border'>
                <div className='truncate px-2 py-1 font-mono text-[11px]'>{c.name || '(未命名)'}</div>
                {c.args && <Pre text={c.args} className='mx-2 mb-2 max-h-40' />}
              </div>
            ))}
          </div>
        </Section>
      )}

      {e.reasoning && (
        <Section title='思考过程' hint={e.reasoning_truncated ? '已截断' : undefined} copy={e.reasoning}>
          <MiniButton onClick={() => setShowThinking((v) => !v)}>
            {showThinking ? '收起思考' : `展开思考（${e.reasoning.length} 字符）`}
          </MiniButton>
          {showThinking && <Pre text={e.reasoning} className='mt-1' />}
        </Section>
      )}
    </div>
  )
}

function Row({ e }: { e: LlmEvent }) {
  const [open, setOpen] = useState(false)
  return (
    <div className='min-w-0 rounded-md border px-3 py-2'>
      <div
        className='hover:bg-muted/40 -mx-1 min-w-0 cursor-pointer rounded px-1'
        onClick={() => setOpen((v) => !v)}
      >
        <div className='flex min-w-0 flex-wrap items-center gap-2 text-xs'>
          <span className='text-muted-foreground w-3 shrink-0 font-mono'>{open ? '▾' : '▸'}</span>
          <Badge variant='outline' className={cn('shrink-0 font-mono', agentClass(e.agent))}>
            {e.agent ?? 'unknown'}
          </Badge>
          {e.challenge_id != null && (
            <Badge variant='outline' className='shrink-0 font-mono'>
              #{e.challenge_id}
            </Badge>
          )}
          <span className='text-muted-foreground shrink-0'>{formatTime(e.ts)}</span>
          <span className='text-muted-foreground max-w-[16rem] truncate'>{e.model ?? ''}</span>
          {e.message_count != null && (
            <span className='text-muted-foreground shrink-0'>{e.message_count} 条消息</span>
          )}
          {e.dur != null && (
            <span className='text-muted-foreground shrink-0'>耗时 {formatDuration(e.dur)}</span>
          )}
          {e.tokens != null && (
            <span className='text-muted-foreground shrink-0'>tokens {e.tokens}</span>
          )}
          {e.status != null && e.status !== 200 && (
            <span className='shrink-0 text-rose-500'>HTTP {e.status}</span>
          )}
          {e.status == null && <span className='shrink-0 text-amber-500'>进行中…</span>}
        </div>
        <div className={cn('text-muted-foreground mt-1 min-w-0 text-xs', !open && 'truncate')}>
          {e.error ? (
            <span className='text-rose-500'>{e.error}</span>
          ) : (
            <>→ {e.preview || '（无预览）'}</>
          )}
        </div>
        {e.resp_preview && !open && (
          <div className='text-muted-foreground mt-0.5 truncate text-xs'>← {e.resp_preview}</div>
        )}
      </div>
      {open && <Detail e={e} />}
    </div>
  )
}

export function LlmFeed({
  events,
  empty = '暂无 AI 请求',
  heightClass = 'h-[60vh]',
}: {
  events: LlmEvent[]
  empty?: string
  heightClass?: string
}) {
  if (!events.length) {
    return <div className='text-muted-foreground p-6 text-center text-sm'>{empty}</div>
  }
  return (
    <div className={cn('w-full min-w-0 overflow-x-hidden overflow-y-auto pr-3', heightClass)}>
      <div className='min-w-0 space-y-2'>
        {events.map((e) => (
          <Row key={e.id} e={e} />
        ))}
      </div>
    </div>
  )
}
