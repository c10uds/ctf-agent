import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

interface DialogProps {
  open: boolean
  onClose: () => void
  title?: string
  description?: string
  className?: string
  children?: ReactNode
}

export function Dialog({ open, onClose, title, description, className, children }: DialogProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="animate-fade-in absolute inset-0 bg-black/50" onClick={onClose} />
      <div
        role="dialog"
        className={cn(
          'animate-fade-in relative z-10 w-full max-w-lg rounded-xl bg-white p-6 shadow-xl',
          className,
        )}
      >
        <button
          onClick={onClose}
          aria-label="关闭"
          className="absolute right-4 top-4 text-slate-400 transition-colors hover:text-slate-600"
        >
          <X className="h-4 w-4" />
        </button>
        {title && <h2 className="pr-6 text-lg font-semibold text-slate-900">{title}</h2>}
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
        {children && <div className={cn(title || description ? 'mt-4' : '')}>{children}</div>}
      </div>
    </div>,
    document.body,
  )
}
