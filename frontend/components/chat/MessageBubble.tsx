'use client'

import { Message } from '@/types'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MessageBubbleProps {
  message: Message
  isStreaming?: boolean
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}
    >
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-f1-red text-white rounded-br-md'
            : 'bg-bg-secondary text-white rounded-bl-md'
        }`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block w-2 h-4 ml-1 bg-f1-red animate-pulse" />
            )}
          </div>
        )}

        {/* Metadata badge */}
        {!isUser && message.metadata?.queryType && !isStreaming && (
          <div className="mt-2 pt-2 border-t border-white/10">
            <span className="text-xs text-f1-gray">
              {message.metadata.queryType.replace('QueryType.', '')}
              {message.metadata.confidence && (
                <span className="ml-2 opacity-60">
                  {Math.round(message.metadata.confidence * 100)}% confidence
                </span>
              )}
            </span>
          </div>
        )}
      </div>
    </motion.div>
  )
}
