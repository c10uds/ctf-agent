import { createFileRoute } from '@tanstack/react-router'
import { ChatPanel } from '@/features/ctf/chat-panel'

function ChatPage() {
  return (
    <div className='space-y-4'>
      <h2 className='text-lg font-semibold'>Chat</h2>
      <ChatPanel />
    </div>
  )
}

export const Route = createFileRoute('/_authenticated/chat')({
  component: ChatPage,
})
