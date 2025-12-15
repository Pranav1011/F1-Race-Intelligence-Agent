'use client'

import { useEffect, useRef, useMemo } from 'react'
import { Message } from '@/types'
import { MessageBubble } from './MessageBubble'
import { MessageInput } from './MessageInput'
import { TypingIndicator } from './TypingIndicator'
import { SuggestedPrompts } from './SuggestedPrompts'

// Query context type matching TypingIndicator
type QueryContext =
  | 'comparison'
  | 'strategy'
  | 'pace'
  | 'telemetry'
  | 'results'
  | 'general'

interface ChatAreaProps {
  messages: Message[]
  isStreaming: boolean
  onSendMessage: (content: string) => void
  toolInProgress?: string
}

// Infer query context from the last user message
function inferQueryContext(userMessage: string): QueryContext {
  const msg = userMessage.toLowerCase()

  // Comparison keywords
  if (
    msg.includes('compare') ||
    msg.includes('versus') ||
    msg.includes(' vs ') ||
    msg.includes('head to head') ||
    msg.includes('head-to-head') ||
    msg.includes('faster than') ||
    msg.includes('slower than')
  ) {
    return 'comparison'
  }

  // Strategy keywords
  if (
    msg.includes('strategy') ||
    msg.includes('tire') ||
    msg.includes('tyre') ||
    msg.includes('pit stop') ||
    msg.includes('pitstop') ||
    msg.includes('stint') ||
    msg.includes('compound') ||
    msg.includes('undercut') ||
    msg.includes('overcut')
  ) {
    return 'strategy'
  }

  // Pace keywords
  if (
    msg.includes('pace') ||
    msg.includes('lap time') ||
    msg.includes('fastest lap') ||
    msg.includes('average') ||
    msg.includes('consistency') ||
    msg.includes('delta')
  ) {
    return 'pace'
  }

  // Telemetry keywords
  if (
    msg.includes('telemetry') ||
    msg.includes('speed') ||
    msg.includes('throttle') ||
    msg.includes('brake') ||
    msg.includes('gear') ||
    msg.includes('trace')
  ) {
    return 'telemetry'
  }

  // Results keywords
  if (
    msg.includes('result') ||
    msg.includes('standing') ||
    msg.includes('championship') ||
    msg.includes('winner') ||
    msg.includes('podium') ||
    msg.includes('points') ||
    msg.includes('position')
  ) {
    return 'results'
  }

  return 'general'
}

export function ChatArea({
  messages,
  isStreaming,
  onSendMessage,
  toolInProgress,
}: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  const isEmpty = messages.length === 0

  // Get the last user message for context inference
  const queryContext = useMemo<QueryContext>(() => {
    const lastUserMessage = [...messages]
      .reverse()
      .find((m) => m.role === 'user')
    if (lastUserMessage) {
      return inferQueryContext(lastUserMessage.content)
    }
    return 'general'
  }, [messages])

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {isEmpty ? (
          <SuggestedPrompts onSelect={onSendMessage} />
        ) : (
          <div className="p-4">
            {messages.map((msg, idx) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                isStreaming={
                  isStreaming &&
                  idx === messages.length - 1 &&
                  msg.role === 'assistant'
                }
              />
            ))}
            {isStreaming && messages[messages.length - 1]?.role === 'user' && (
              <TypingIndicator
                queryContext={queryContext}
                toolInProgress={toolInProgress}
              />
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <MessageInput onSend={onSendMessage} disabled={isStreaming} />
    </div>
  )
}
