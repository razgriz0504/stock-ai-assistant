import { ReactNode, useState } from 'react'

interface Tab {
  id: string
  label: string
}

interface TabsProps {
  tabs: Tab[]
  defaultTab?: string
  children: (activeTab: string) => ReactNode
}

export function Tabs({ tabs, defaultTab, children }: TabsProps) {
  const [active, setActive] = useState(defaultTab || tabs[0]?.id || '')

  return (
    <div>
      <div className="flex gap-0 border-b-2 border-cream-300 mb-8">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            className={`
              font-mono text-xs tracking-[1px] uppercase
              px-5 py-3 cursor-pointer border-b-2 -mb-[2px]
              transition-all duration-150
              ${
                active === tab.id
                  ? 'text-copper border-copper'
                  : 'text-gray-500 border-transparent hover:text-gray-900'
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {children(active)}
    </div>
  )
}
