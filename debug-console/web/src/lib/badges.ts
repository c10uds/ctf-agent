import type { BadgeVariant } from '../components/ui/badge'

/** 题目状态：SOLVED 绿 / 进行中 黄 / 阻塞 红 / TODO 灰 / SKIP 灰线 */
export function challengeStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case 'SOLVED':
      return 'success'
    case 'ANALYZING':
    case 'ATTACKING':
    case 'LOCAL_READY':
      return 'warning'
    case 'BLOCKED':
    case 'STUCK':
      return 'destructive'
    case 'SKIP':
      return 'outline'
    default:
      return 'secondary'
  }
}

/** 题目分类：pwn 紫 / web 蓝 */
export function categoryVariant(category: string): BadgeVariant {
  if (category === 'pwn') return 'purple'
  if (category === 'web') return 'info'
  return 'secondary'
}

export function sliverStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case 'active':
      return 'success'
    case 'finished':
      return 'outline'
    default:
      return 'secondary'
  }
}

/** 活动 kind：tool 蓝 / text 绿 / reasoning 灰 / user 橙 */
export function activityKindVariant(kind: string): BadgeVariant {
  switch (kind) {
    case 'tool':
      return 'info'
    case 'text':
      return 'success'
    case 'user':
      return 'orange'
    default:
      return 'secondary'
  }
}

export function activityKindLabel(kind: string): string {
  switch (kind) {
    case 'tool':
      return '工具'
    case 'text':
      return '回复'
    case 'reasoning':
      return '思考'
    case 'user':
      return '派发'
    default:
      return kind
  }
}
