import { createFileRoute } from '@tanstack/react-router'
import { ChallengeDetail } from '@/features/ctf/challenge-detail'

export const Route = createFileRoute('/_authenticated/challenges/$challengeId')({
  component: ChallengePage,
})

function ChallengePage() {
  const { challengeId } = Route.useParams()
  return <ChallengeDetail challengeId={Number(challengeId)} />
}
