import { createFileRoute } from '@tanstack/react-router'
import { EnvironmentsPanel } from '@/features/ctf/environments-panel'

function EnvironmentsPage() {
  return (
    <div className='space-y-4'>
      <h2 className='text-lg font-semibold'>环境</h2>
      <EnvironmentsPanel />
    </div>
  )
}

export const Route = createFileRoute('/_authenticated/environments')({
  component: EnvironmentsPage,
})
