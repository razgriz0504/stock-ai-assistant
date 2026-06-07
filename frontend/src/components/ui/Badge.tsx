import { ReactNode } from 'react'

interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'success' | 'danger' | 'warning' | 'copper'
  className?: string
}

const variantStyles = {
  default: 'bg-cream-200 text-gray-600',
  success: 'bg-green-50 text-success',
  danger: 'bg-red-50 text-danger',
  warning: 'bg-amber-50 text-warning',
  copper: 'bg-orange-50 text-copper',
}

export function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center
        font-mono text-[10px] font-semibold tracking-wide uppercase
        px-2 py-0.5 rounded
        ${variantStyles[variant]}
        ${className}
      `}
    >
      {children}
    </span>
  )
}
