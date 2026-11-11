'use client'

import { useEffect, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Message, QueryInterpretation as QueryInterpretationType } from '@/types'
import { MessageBubble } from './MessageBubble'
import { MessageInput } from './MessageInput'
import { StatusIndicator } from './StatusIndicator'
import { SuggestedPrompts } from './SuggestedPrompts'
import { QueryInterpretation } from './QueryInterpretation'

interface ChatAreaProps {
  messages: Message[]
  isStreaming: boolean
  // True while any session is streaming: one answer is in flight at a time
  inputDisabled: boolean
  // True when the answer in flight belongs to another chat
  answeringElsewhere?: boolean
  onSendMessage: (content: string) => void
  statusMessage?: string | null
  interpretation?: QueryInterpretationType | null
  showInterpretation?: boolean
}

function EmptyState({
  onSelect,
  disabled,
}: {
  onSelect: (content: string) => void
  disabled: boolean
}) {
  return (
    <div className="flex min-h-full flex-col justify-center px-4 py-10 sm:px-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="mx-auto w-full max-w-2xl"
      >
        <p className="mb-3 font-mono text-xs uppercase tracking-[0.18em] text-f1-redLight">
          Pit wall · 2018–2024
        </p>
        <h2 className="text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
          Ask about any race.
        </h2>
        <p className="mt-3 max-w-xl leading-relaxed text-text-secondary">
          Lap times, tyre strategy, pit stops and results. Answers are built from the race data
          you have ingested, and say so when that data is missing. Charts open beside the chat
          when there is something to plot.
        </p>

        <h3 className="mb-2 mt-8 text-xs font-medium uppercase tracking-wider text-text-muted">
          Try one
        </h3>
        <SuggestedPrompts onSelect={onSelect} disabled={disabled} />
      </motion.div>
    </div>
  )
}

export function ChatArea({
  messages,
  isStreaming,
  inputDisabled,
  answeringElsewhere = false,
  onSendMessage,
  statusMessage,
  interpretation,
  showInterpretation = false,
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
    <div className="relative flex flex-col h-full bg-background-primary">
      {/* Messages area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto scrollbar-thin relative z-10"
      >
        {isEmpty ? (
          <EmptyState onSelect={onSendMessage} disabled={inputDisabled} />
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

            {/* Query interpretation feedback */}
            <QueryInterpretation
              interpretation={interpretation || null}
              isVisible={showInterpretation}
            />

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

      {/* Input area */}
      <div className="relative z-20 border-t border-white/5 bg-background-primary">
        <div className="max-w-4xl mx-auto">
          <MessageInput
            onSend={onSendMessage}
            disabled={inputDisabled}
            disabledReason={
              answeringElsewhere
                ? 'Another chat is still answering. You can send here when it finishes.'
                : inputDisabled
                  ? 'Answering… you can send your next question when this finishes.'
                  : null
            }
          />
        </div>
      </div>
    </div>
  )
}

export default ChatArea
