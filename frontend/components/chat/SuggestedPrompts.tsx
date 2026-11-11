'use client'

import { ArrowRight } from 'lucide-react'

interface SuggestedPromptsProps {
  onSelect: (prompt: string) => void
  disabled?: boolean
}

const SUGGESTED_PROMPTS = [
  { category: 'Race result', text: 'Who won the 2024 Bahrain GP?' },
  { category: 'Head-to-head', text: "Compare Verstappen and Norris's lap times at Monaco 2024" },
  { category: 'Strategy', text: "Why did Ferrari's strategy fail at Silverstone?" },
  { category: 'Pit stops', text: 'Show me the fastest pit stops of 2024' },
]

export function SuggestedPrompts({ onSelect, disabled = false }: SuggestedPromptsProps) {
  return (
    <ul className="w-full divide-y divide-white/5 border-y border-white/5">
      {SUGGESTED_PROMPTS.map((prompt) => (
        <li key={prompt.text}>
          <button
            onClick={() => onSelect(prompt.text)}
            disabled={disabled}
            className="group relative flex w-full items-center gap-4 py-3.5 pl-4 pr-3 text-left
                       transition-colors hover:bg-white/[0.03] disabled:cursor-not-allowed
                       disabled:hover:bg-transparent"
          >
            {/* Pit-lane marker: lights up on hover and keyboard focus */}
            <span
              aria-hidden="true"
              className="absolute left-0 top-3 bottom-3 w-0.5 rounded-full bg-white/10 transition-colors
                         group-hover:bg-f1-red group-focus-visible:bg-f1-red group-disabled:bg-white/10"
            />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-4">
              <span className="shrink-0 font-mono text-[11px] uppercase tracking-wider text-text-muted sm:w-28">
                {prompt.category}
              </span>
              <span className="text-sm text-text-primary group-disabled:text-text-secondary">
                {prompt.text}
              </span>
            </span>
            <ArrowRight
              aria-hidden="true"
              className="h-4 w-4 shrink-0 text-text-muted transition-transform duration-200
                         group-hover:translate-x-0.5 group-hover:text-f1-redLight group-disabled:translate-x-0
                         group-disabled:text-text-muted"
            />
          </button>
        </li>
      ))}
    </ul>
  )
}

export default SuggestedPrompts
