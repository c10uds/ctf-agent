import {
  Activity,
  Command,
  LayoutDashboard,
  ListTodo,
  MessagesSquare,
  Server,
} from 'lucide-react'
import { type SidebarData } from '../types'

export const sidebarData: SidebarData = {
  user: {
    name: 'AIxCTF',
    email: 'operator@localhost',
    avatar: '/avatars/shadcn.jpg',
  },
  teams: [
    {
      name: 'AIxCTF 观测台',
      logo: Command,
      plan: 'Live',
    },
  ],
  navGroups: [
    {
      title: '监控',
      items: [
        {
          title: '总览',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          title: '题目',
          url: '/challenges',
          icon: ListTodo,
        },
        {
          title: 'Master 流',
          url: '/master',
          icon: Activity,
        },
        {
          title: '环境',
          url: '/environments',
          icon: Server,
        },
      ],
    },
    {
      title: '交互',
      items: [
        {
          title: 'Chat',
          url: '/chat',
          icon: MessagesSquare,
        },
      ],
    },
  ],
}
