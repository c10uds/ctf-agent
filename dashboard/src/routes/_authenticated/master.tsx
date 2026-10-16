import { createFileRoute } from '@tanstack/react-router'
import { LlmFeed } from '@/features/ctf/llm-feed'
import { useCtfStore } from '@/features/ctf/store'
import { Card, CardContent } from '@/components/ui/card'

function MasterPage() {
  const llm = useCtfStore((s) => s.llm)
  const events = llm.filter((e) => e.agent === 'master')
  return (
    <div className='space-y-4'>
      <h2 className='text-lg font-semibold'>Master 决策流</h2>
      <Card>
        <CardContent className='pt-6'>
          <LlmFeed events={events} empty='暂无 Master 的 AI 请求' />
        </CardContent>
      </Card>
    </div>
  )
}

export const Route = createFileRoute('/_authenticated/master')({
  component: MasterPage,
})
