'use client'

import { useEffect, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Message } from '@/types'
import { MessageBubble } from './MessageBubble'
import { MessageInput } from './MessageInput'
import { StatusIndicator } from './StatusIndicator'
import { SuggestedPrompts } from './SuggestedPrompts'

interface ChatAreaProps {
  messages: Message[]
  isStreaming: boolean
  onSendMessage: (content: string) => void
  statusMessage?: string | null
}

// Background decoration component
function GridBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {/* Grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
        }}
      />

      {/* Racing stripes */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-f1-red to-transparent opacity-30" />

      {/* Subtle corner decorations */}
      <div className="absolute top-4 left-4 w-20 h-20 border-l-2 border-t-2 border-white/5 rounded-tl-xl" />
      <div className="absolute top-4 right-4 w-20 h-20 border-r-2 border-t-2 border-white/5 rounded-tr-xl" />
    </div>
  )
}

// Empty state with F1 branding
function EmptyState({ onSelect }: { onSelect: (content: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-center max-w-2xl"
      >
        {/* Logo/Icon */}
        <motion.div
          className="mb-6"
          animate={{ scale: [1, 1.05, 1] }}
          transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
        >
          <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-f1-red/20 to-orange-500/20 border border-f1-red/30">
            <span className="text-5xl">🏎️</span>
          </div>
        </motion.div>

        <h1 className="text-3xl font-bold text-white mb-2">
          F1 Race Intelligence
        </h1>
        <p className="text-f1-gray text-lg mb-8">
          Your AI pit wall engineer. Ask anything about Formula 1 races,
          strategies, and driver performance.
        </p>

        {/* Quick prompts */}
        <SuggestedPrompts onSelect={onSelect} />
      </motion.div>
    </div>
  )
}

export function ChatArea({
  messages,
  isStreaming,
  onSendMessage,
  statusMessage,
}: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isStreaming, statusMessage])

  const isEmpty = messages.length === 0

  // Check if last message is from user (to show status indicator)
  const showStatus = useMemo(() => {
    if (!isStreaming) return false
    if (!statusMessage) return false
    const lastMsg = messages[messages.length - 1]
    return lastMsg?.role === 'user' || (lastMsg?.role === 'assistant' && lastMsg?.content === '')
  }, [isStreaming, statusMessage, messages])

  return (
    <div className="relative flex flex-col h-full">
      <GridBackground />

      {/* Messages area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto scrollbar-thin relative z-10"
      >
        {isEmpty ? (
          <EmptyState onSelect={onSendMessage} />
        ) : (
          <div className="max-w-4xl mx-auto p-4 md:p-6">
            <AnimatePresence mode="popLayout">
              {messages.map((msg, idx) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3 }}
                >
                  <MessageBubble
                    message={msg}
                    isStreaming={
                      isStreaming &&
                      idx === messages.length - 1 &&
                      msg.role === 'assistant'
                    }
                  />
                </motion.div>
              ))}
            </AnimatePresence>

            {/* Status indicator */}
            <AnimatePresence>
              {showStatus && statusMessage && (
                <StatusIndicator
                  message={statusMessage}
                  isActive={true}
                />
              )}
            </AnimatePresence>

            <div ref={messagesEndRef} className="h-4" />
          </div>
        )}
      </div>

      {/* Input area with gradient backdrop */}
      <div className="relative z-20">
        {/* Gradient fade */}
        <div className="absolute bottom-full left-0 right-0 h-20 bg-gradient-to-t from-background-primary to-transparent pointer-events-none" />

        <div className="bg-background-primary/80 backdrop-blur-xl border-t border-white/5">
          <div className="max-w-4xl mx-auto">
            <MessageInput onSend={onSendMessage} disabled={isStreaming} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default ChatArea
