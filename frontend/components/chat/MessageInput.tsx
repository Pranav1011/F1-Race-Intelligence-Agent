'use client'

import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { Send } from 'lucide-react'

interface MessageInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  // Shown under the input while sending is paused, e.g. another chat is answering
  disabledReason?: string | null
  placeholder?: string
}

export function MessageInput({
  onSend,
  disabled = false,
  disabledReason = null,
  placeholder = 'Ask about F1 races, strategies, telemetry...',
}: MessageInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 150)}px`
    }
  }, [input])

  const handleSubmit = () => {
    const trimmed = input.trim()
    if (trimmed && !disabled) {
      onSend(trimmed)
      setInput('')
      // Reset height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const canSubmit = input.trim().length > 0 && !disabled

  return (
    <div className="p-4">
      <div
        className="relative flex items-end gap-3 rounded-2xl bg-surface border border-white/10
                   transition-colors focus-within:border-f1-red"
      >
        {/* Left accent bar */}
        <div
          aria-hidden="true"
          className="absolute left-0 top-3 bottom-3 w-1 rounded-full bg-f1-red/60"
        />

        {/* Textarea: stays editable while an answer streams so the next question can be drafted */}
        <div className="flex-1 pl-5 py-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            aria-label="Ask a question about F1"
            aria-describedby={disabledReason ? 'message-input-status' : undefined}
            rows={1}
            className="w-full resize-none bg-transparent text-text-primary placeholder:text-text-muted
                       text-sm leading-relaxed focus:outline-none focus-visible:ring-0
                       focus-visible:ring-offset-0 max-h-[150px] scrollbar-thin"
          />
        </div>

        <div className="flex items-center pr-3 pb-3">
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            aria-label="Send message"
            className={`p-3 rounded-xl transition-colors duration-200 ${
              canSubmit
                ? 'bg-f1-red hover:bg-f1-redDark text-white'
                : 'bg-white/5 text-text-muted cursor-not-allowed'
            }`}
          >
            <Send className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Status line: why sending is paused, otherwise the keyboard hints */}
      <div className="flex min-h-[1.25rem] items-center mt-2 px-2 text-xs">
        {disabledReason ? (
          <p id="message-input-status" role="status" className="text-text-secondary">
            {disabledReason}
          </p>
        ) : (
          <div className="hidden sm:flex items-center gap-4 text-text-muted">
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-surface rounded text-[11px] font-mono text-text-secondary">Enter</kbd>
              <span>to send</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-surface rounded text-[11px] font-mono text-text-secondary">Shift + Enter</kbd>
              <span>new line</span>
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export default MessageInput
