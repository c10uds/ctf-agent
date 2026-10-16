import type { HTMLAttributes } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const badgeVariants = cva(
  'inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-slate-900 text-white',
        secondary: 'border-transparent bg-slate-100 text-slate-600',
        outline: 'border-slate-300 text-slate-500',
        success: 'border-transparent bg-emerald-100 text-emerald-700',
        warning: 'border-transparent bg-amber-100 text-amber-700',
        destructive: 'border-transparent bg-red-100 text-red-700',
        info: 'border-transparent bg-blue-100 text-blue-700',
        purple: 'border-transparent bg-purple-100 text-purple-700',
        orange: 'border-transparent bg-orange-100 text-orange-700',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export type BadgeVariant = VariantProps<typeof badgeVariants>['variant']

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
