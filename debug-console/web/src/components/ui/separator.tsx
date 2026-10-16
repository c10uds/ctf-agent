import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

interface SeparatorProps extends HTMLAttributes<HTMLDivElement> {
  orientation?: 'horizontal' | 'vertical'
}

export function Separator({ orientation = 'horizontal', className, ...props }: SeparatorProps) {
  return (
    <div
      role="separator"
      className={cn(
        'shrink-0 bg-slate-200',
        orientation === 'vertical' ? 'h-full w-px' : 'h-px w-full',
        className,
      )}
      {...props}
    />
  )
}
