import { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  hover?: boolean
}

export function Card({ children, className = '', hover = false }: CardProps) {
  return (
    <div
      className={`
        bg-white border border-cream-300 rounded-lg p-6
        shadow-card transition-all duration-150
        ${hover ? 'hover:shadow-card-hover hover:border-copper/30' : ''}
        ${className}
      `}
    >
      {children}
    </div>
  )
}

interface CardHeaderProps {
  title: string
  action?: ReactNode
  label?: string
}

export function CardHeader({ title, action, label }: CardHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-5">
      <div>
        {label && (
          <span className="font-mono text-[10px] tracking-[1.5px] uppercase text-copper block mb-1">
            {label}
          </span>
        )}
        <h3 className="font-heading text-lg font-semibold">{title}</h3>
      </div>
      {action && <div>{action}</div>}
    </div>
  )
}
