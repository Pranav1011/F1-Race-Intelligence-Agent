'use client'

import { useEffect, useRef } from 'react'
import { Message } from '@/types'
import { MessageBubble } from './MessageBubble'
import { MessageInput } from './MessageInput'
import { TypingIndicator } from './TypingIndicator'
import { SuggestedPrompts } from './SuggestedPrompts'

interface ChatAreaProps {
  messages: Message[]
  isStreaming: boolean
  onSendMessage: (content: string) => void
}

export function ChatArea({ messages, isStreaming, onSendMessage }: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  const isEmpty = messages.length === 0

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
              <TypingIndicator />
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
