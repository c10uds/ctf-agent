import { createFileRoute } from '@tanstack/react-router'
import { Overview } from '@/features/ctf/overview'

export const Route = createFileRoute('/_authenticated/')({
  component: Overview,
})
