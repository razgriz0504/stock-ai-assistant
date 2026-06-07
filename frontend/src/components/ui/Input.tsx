import { InputHTMLAttributes, forwardRef } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, className = '', ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="block font-mono text-[10px] tracking-[1.5px] uppercase text-gray-500">
            {label}
          </label>
        )}
        <input
          ref={ref}
          className={`
            w-full px-3.5 py-2.5 text-sm
            bg-white border border-cream-300 rounded-md
            placeholder:text-cream-500
            focus:outline-none focus:border-copper
            transition-colors duration-150
            ${error ? 'border-danger' : ''}
            ${className}
          `}
          {...props}
        />
        {hint && !error && (
          <p className="text-xs text-cream-500">{hint}</p>
        )}
        {error && (
          <p className="text-xs text-danger">{error}</p>
        )}
      </div>
    )
  },
)

Input.displayName = 'Input'

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  hint?: string
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, hint, className = '', ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="block font-mono text-[10px] tracking-[1.5px] uppercase text-gray-500">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          className={`
            w-full px-3.5 py-2.5 text-sm
            bg-white border border-cream-300 rounded-md
            placeholder:text-cream-500
            focus:outline-none focus:border-copper
            transition-colors duration-150
            min-h-[120px] resize-y leading-relaxed
            ${className}
          `}
          {...props}
        />
        {hint && <p className="text-xs text-cream-500">{hint}</p>}
      </div>
    )
  },
)

Textarea.displayName = 'Textarea'
