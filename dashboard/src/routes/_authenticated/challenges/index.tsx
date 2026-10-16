import { createFileRoute } from '@tanstack/react-router'
import { ChallengesTable } from '@/features/ctf/challenges-table'
import { useCtfStore } from '@/features/ctf/store'
import { Card, CardContent } from '@/components/ui/card'

function ChallengesPage() {
  const rows = useCtfStore((s) => s.scoreboard)
  return (
    <div className='space-y-4'>
      <h2 className='text-lg font-semibold'>题目</h2>
      <Card>
        <CardContent className='pt-6'>
          <ChallengesTable rows={rows} />
        </CardContent>
      </Card>
    </div>
  )
}

export const Route = createFileRoute('/_authenticated/challenges/')({
  component: ChallengesPage,
})
