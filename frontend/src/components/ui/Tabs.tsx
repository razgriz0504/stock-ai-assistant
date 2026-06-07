import { ReactNode, useState } from 'react'

interface Tab {
  id: string
  label: string
}

export interface TabsProps {
  tabs: Tab[]
  defaultTab?: string
  activeTab?: string
  onChange?: (tab: string) => void
  children?: (activeTab: string) => ReactNode
}

export function Tabs({ tabs, defaultTab, activeTab, onChange, children }: TabsProps) {
  const [internalActive, setInternalActive] = useState(defaultTab || tabs[0]?.id || '')
  const current = activeTab ?? internalActive

  const handleClick = (id: string) => {
    if (onChange) {
      onChange(id)
    } else {
      setInternalActive(id)
    }
  }

  return (
    <div>
      <div className="flex gap-0 border-b-2 border-cream-300 mb-8">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleClick(tab.id)}
            className={`
              font-mono text-xs tracking-[1px] uppercase
              px-5 py-3 cursor-pointer border-b-2 -mb-[2px]
              transition-all duration-150
              ${
                current === tab.id
                  ? 'text-copper border-copper'
                  : 'text-gray-500 border-transparent hover:text-gray-900'
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {children && children(current)}
    </div>
  )
}
