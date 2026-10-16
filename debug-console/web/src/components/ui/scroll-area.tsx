import { forwardRef, type HTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

/** 简化版 ScrollArea：原生滚动 + 细滚动条样式 */
export const ScrollArea = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('scroll-thin overflow-auto', className)} {...props} />
  ),
)
ScrollArea.displayName = 'ScrollArea'
