'use client'

import { useMemo } from 'react'
import { Message } from '@/types'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MessageBubbleProps {
  message: Message
  isStreaming?: boolean
}

// Custom markdown components for better styling
const markdownComponents = {
  h1: ({ children }: any) => (
    <h1 className="text-2xl font-bold text-text-primary mb-4 mt-6 first:mt-0 border-b border-white/10 pb-2">
      {children}
    </h1>
  ),
  h2: ({ children }: any) => (
    <h2 className="text-xl font-bold text-text-primary mb-3 mt-5 first:mt-0 flex items-center gap-2">
      <span className="w-1 h-6 bg-f1-red rounded-full" />
      {children}
    </h2>
  ),
  h3: ({ children }: any) => (
    <h3 className="text-lg font-semibold text-text-primary mb-2 mt-4 first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }: any) => (
    <p className="text-text-primary/90 mb-3 leading-relaxed last:mb-0">{children}</p>
  ),
  ul: ({ children }: any) => (
    <ul className="space-y-2 mb-4 ml-4">{children}</ul>
  ),
  ol: ({ children }: any) => (
    <ol className="space-y-2 mb-4 ml-4 list-decimal">{children}</ol>
  ),
  li: ({ children }: any) => (
    <li className="text-text-primary/90 flex items-start gap-2">
      <span className="text-f1-red mt-1.5">•</span>
      <span>{children}</span>
    </li>
  ),
  strong: ({ children }: any) => (
    <strong className="font-bold text-text-primary">{children}</strong>
  ),
  em: ({ children }: any) => (
    <em className="text-text-secondary italic">{children}</em>
  ),
  code: ({ inline, children }: any) =>
    inline ? (
      <code className="bg-surface px-1.5 py-0.5 rounded text-sm font-mono text-accent-orange">
        {children}
      </code>
    ) : (
      <code className="block bg-background-primary/50 p-4 rounded-lg text-sm font-mono text-data-positive overflow-x-auto my-3 border border-white/5">
        {children}
      </code>
    ),
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-4 border-f1-red pl-4 my-4 bg-surface/50 py-2 rounded-r-lg">
      {children}
    </blockquote>
  ),
  table: ({ children }: any) => (
    <div className="overflow-x-auto my-4 rounded-lg border border-white/5">
      <table className="w-full border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }: any) => (
    <thead className="bg-surface border-b border-white/10">{children}</thead>
  ),
  th: ({ children }: any) => (
    <th className="px-4 py-2 text-left text-sm font-semibold text-text-primary">
      {children}
    </th>
  ),
  td: ({ children }: any) => (
    <td className="px-4 py-2 text-sm text-text-secondary border-b border-white/5">
      {children}
    </td>
  ),
}

// Typing cursor animation
function TypingCursor() {
  return (
    <motion.span
      className="inline-block w-0.5 h-4 ml-0.5 bg-f1-red rounded-full"
      animate={{ opacity: [1, 0, 1] }}
      transition={{ duration: 0.8, repeat: Infinity }}
    />
  )
}

// Confidence badge styling
function ConfidenceBadge({ confidence }: { confidence: number }) {
  const percentage = Math.round(confidence * 100)
  const color =
    percentage >= 80
      ? 'text-data-positive bg-data-positive/10 border-data-positive/30'
      : percentage >= 50
        ? 'text-data-warning bg-data-warning/10 border-data-warning/30'
        : 'text-data-negative bg-data-negative/10 border-data-negative/30'

  return (
    <span className={`text-xs px-2.5 py-1 rounded-full border ${color}`}>
      {percentage}% confidence
    </span>
  )
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  // Parse query type for display
  const queryType = useMemo(() => {
    const qt = message.metadata?.queryType
    if (!qt) return null
    return qt.replace('AnalysisType.', '').replace('QueryType.', '').toLowerCase()
  }, [message.metadata?.queryType])

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-6`}
    >
      <div
        className={`relative max-w-[85%] ${
          isUser ? 'order-2' : 'order-1'
        }`}
      >
        {/* Avatar */}
        <div
          className={`absolute top-0 ${
            isUser ? '-right-12' : '-left-12'
          } w-8 h-8 rounded-xl flex items-center justify-center ${
            isUser
              ? 'bg-gradient-to-br from-f1-red to-f1-redDark'
              : 'bg-surface border border-white/10'
          }`}
        >
          {isUser ? (
            <span className="text-white text-sm">👤</span>
          ) : (
            <span className="text-lg">🏎️</span>
          )}
        </div>

        {/* Message bubble */}
        <div
          className={`relative overflow-hidden ${
            isUser
              ? 'bg-gradient-to-br from-f1-red to-f1-redDark text-white rounded-2xl rounded-br-md'
              : 'bg-surface text-text-primary rounded-2xl rounded-bl-md border border-white/5'
          }`}
          style={{
            boxShadow: isUser
              ? '0 4px 20px rgba(227, 25, 55, 0.2)'
              : '0 4px 20px rgba(0, 0, 0, 0.2)',
          }}
        >
          {/* Subtle gradient overlay for assistant messages */}
          {!isUser && (
            <div className="absolute inset-0 bg-gradient-to-r from-f1-red/5 to-transparent pointer-events-none" />
          )}

          <div className="relative px-5 py-4">
            {isUser ? (
              <p className="text-sm whitespace-pre-wrap leading-relaxed">
                {message.content}
              </p>
            ) : (
              <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents}
                >
                  {message.content}
                </ReactMarkdown>
                {isStreaming && <TypingCursor />}
              </div>
            )}
          </div>
        </div>

        {/* Metadata footer for assistant messages */}
        {!isUser && !isStreaming && message.metadata && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="flex items-center gap-3 mt-2 px-2"
          >
            {queryType && (
              <span className="text-xs text-text-muted capitalize flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-f1-red" />
                {queryType}
              </span>
            )}
            {message.metadata.confidence !== undefined && (
              <ConfidenceBadge confidence={message.metadata.confidence} />
            )}
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}

export default MessageBubble
