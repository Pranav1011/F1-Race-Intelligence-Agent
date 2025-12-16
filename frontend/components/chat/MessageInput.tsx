'use client'

import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { Send, Mic, Zap } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface MessageInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export function MessageInput({
  onSend,
  disabled = false,
  placeholder = 'Ask about F1 races, strategies, telemetry...',
}: MessageInputProps) {
  const [input, setInput] = useState('')
  const [isFocused, setIsFocused] = useState(false)
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
      {/* Main input container with animated border */}
      <div className="relative">
        {/* Animated border gradient when focused */}
        <AnimatePresence>
          {isFocused && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute -inset-[1px] rounded-2xl overflow-hidden"
            >
              <motion.div
                className="absolute inset-0"
                style={{
                  background: 'linear-gradient(90deg, #e10600, #ff6b35, #e10600, #ff6b35)',
                  backgroundSize: '300% 100%',
                }}
                animate={{
                  backgroundPosition: ['0% 0%', '100% 0%'],
                }}
                transition={{
                  duration: 3,
                  repeat: Infinity,
                  ease: 'linear',
                }}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Input container */}
        <div
          className={`relative flex items-end gap-3 rounded-2xl transition-all duration-300 ${
            isFocused
              ? 'bg-background-secondary'
              : 'bg-background-tertiary/50'
          }`}
          style={{
            boxShadow: isFocused
              ? '0 0 30px rgba(225, 6, 0, 0.15), inset 0 0 0 1px rgba(255,255,255,0.1)'
              : 'inset 0 0 0 1px rgba(255,255,255,0.05)',
          }}
        >
          {/* Left accent bar */}
          <div className="absolute left-0 top-3 bottom-3 w-1 bg-gradient-to-b from-f1-red via-orange-500 to-f1-red rounded-full opacity-50" />

          {/* Textarea */}
          <div className="flex-1 pl-5 py-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={placeholder}
              disabled={disabled}
              rows={1}
              className="w-full resize-none bg-transparent text-white placeholder-f1-gray/40
                         text-sm leading-relaxed focus:outline-none disabled:opacity-50
                         disabled:cursor-not-allowed max-h-[150px] scrollbar-thin"
            />
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 pr-3 pb-3">
            {/* Voice input button (decorative for now) */}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="p-2 text-f1-gray/50 hover:text-white/70 transition-colors rounded-lg
                         hover:bg-white/5"
              title="Voice input (coming soon)"
            >
              <Mic className="w-5 h-5" />
            </motion.button>

            {/* Send button */}
            <motion.button
              onClick={handleSubmit}
              disabled={!canSubmit}
              whileHover={canSubmit ? { scale: 1.05 } : {}}
              whileTap={canSubmit ? { scale: 0.95 } : {}}
              className={`relative p-3 rounded-xl transition-all duration-300 ${
                canSubmit
                  ? 'bg-gradient-to-r from-f1-red to-red-600 text-white shadow-lg'
                  : 'bg-white/5 text-f1-gray/30 cursor-not-allowed'
              }`}
              style={{
                boxShadow: canSubmit
                  ? '0 4px 20px rgba(225, 6, 0, 0.4)'
                  : 'none',
              }}
            >
              {/* Glow effect when active */}
              {canSubmit && (
                <motion.div
                  className="absolute inset-0 rounded-xl bg-f1-red/20"
                  animate={{ scale: [1, 1.2, 1], opacity: [0.5, 0, 0.5] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
              )}
              <Send className="relative w-5 h-5" />
            </motion.button>
          </div>
        </div>
      </div>

      {/* Keyboard hints */}
      <div className="flex items-center justify-between mt-2 px-2">
        <div className="flex items-center gap-4 text-xs text-f1-gray/40">
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-white/5 rounded text-[10px] font-mono">Enter</kbd>
            <span>to send</span>
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-white/5 rounded text-[10px] font-mono">Shift + Enter</kbd>
            <span>new line</span>
          </span>
        </div>
        <div className="flex items-center gap-1 text-xs text-f1-gray/40">
          <Zap className="w-3 h-3 text-f1-red" />
          <span>Powered by F1 Intelligence</span>
        </div>
      </div>
    </div>
  )
}

export default MessageInput
