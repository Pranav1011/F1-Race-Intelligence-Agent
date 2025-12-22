'use client'

import { useEffect, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Message, QueryInterpretation as QueryInterpretationType } from '@/types'
import { MessageBubble } from './MessageBubble'
import { MessageInput } from './MessageInput'
import { StatusIndicator } from './StatusIndicator'
import { SuggestedPrompts } from './SuggestedPrompts'
import { QueryInterpretation } from './QueryInterpretation'
import {
  Gauge,
  Trophy,
  Timer,
  Users,
  TrendingUp,
  Zap,
  BarChart3,
  Activity,
} from 'lucide-react'

interface ChatAreaProps {
  messages: Message[]
  isStreaming: boolean
  onSendMessage: (content: string) => void
  statusMessage?: string | null
  interpretation?: QueryInterpretationType | null
  showInterpretation?: boolean
}

// Animated background with subtle grid
function AnimatedBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {/* Gradient orbs */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-f1-red/5 rounded-full blur-[120px] animate-pulse" />
      <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-accent-purple/5 rounded-full blur-[100px] animate-pulse" style={{ animationDelay: '1s' }} />

      {/* Grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
        }}
      />

      {/* Top racing stripe */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-f1-red/50 to-transparent" />
    </div>
  )
}

// Feature card for empty state
function FeatureCard({
  icon: Icon,
  title,
  description,
  gradient,
}: {
  icon: typeof Gauge
  title: string
  description: string
  gradient: string
}) {
  return (
    <motion.div
      whileHover={{ scale: 1.02, y: -2 }}
      className="relative group p-4 rounded-xl bg-surface/50 border border-white/5
                 hover:border-white/10 transition-all duration-300 cursor-default"
    >
      {/* Hover glow */}
      <div className={`absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100
                       transition-opacity duration-300 bg-gradient-to-br ${gradient} blur-xl -z-10`} />

      <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${gradient}
                       flex items-center justify-center mb-3`}>
        <Icon className="w-5 h-5 text-white" />
      </div>
      <h3 className="text-sm font-semibold text-text-primary mb-1">{title}</h3>
      <p className="text-xs text-text-muted leading-relaxed">{description}</p>
    </motion.div>
  )
}

// Stats badge for empty state
function StatBadge({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col items-center p-3 rounded-lg bg-surface/30 border border-white/5">
      <span className="text-lg font-bold text-text-primary">{value}</span>
      <span className="text-[10px] text-text-muted uppercase tracking-wider">{label}</span>
    </div>
  )
}

// Stunning empty state with F1 branding
function EmptyState({ onSelect }: { onSelect: (content: string) => void }) {
  const features = [
    {
      icon: Gauge,
      title: 'Lap Analysis',
      description: 'Deep dive into lap times, sector splits, and pace evolution',
      gradient: 'from-f1-red/20 to-accent-orange/20',
    },
    {
      icon: Users,
      title: 'Driver Comparisons',
      description: 'Head-to-head analysis between any drivers',
      gradient: 'from-accent-blue/20 to-accent-cyan/20',
    },
    {
      icon: TrendingUp,
      title: 'Strategy Insights',
      description: 'Pit stop strategies, tire compounds, and race dynamics',
      gradient: 'from-accent-emerald/20 to-accent-cyan/20',
    },
    {
      icon: BarChart3,
      title: 'Visualizations',
      description: 'Interactive charts and data visualizations',
      gradient: 'from-accent-purple/20 to-accent-blue/20',
    },
  ]

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-12">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="text-center max-w-3xl w-full"
      >
        {/* Hero Section */}
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="mb-8"
        >
          {/* Logo/Icon with glow */}
          <div className="relative inline-flex mb-6">
            <div className="absolute inset-0 bg-f1-red/30 rounded-full blur-2xl scale-150" />
            <motion.div
              animate={{
                boxShadow: [
                  '0 0 30px rgba(227, 25, 55, 0.3)',
                  '0 0 50px rgba(227, 25, 55, 0.5)',
                  '0 0 30px rgba(227, 25, 55, 0.3)',
                ]
              }}
              transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
              className="relative w-20 h-20 rounded-2xl bg-gradient-to-br from-f1-red to-f1-redDark
                         flex items-center justify-center border border-white/10"
            >
              <Activity className="w-10 h-10 text-white" />
            </motion.div>
          </div>

          {/* Title with gradient */}
          <h1 className="text-4xl md:text-5xl font-bold mb-3">
            <span className="text-gradient">F1 Race Intelligence</span>
          </h1>
          <p className="text-lg text-text-secondary max-w-xl mx-auto leading-relaxed">
            Your AI-powered pit wall engineer. Analyze races, compare drivers,
            and uncover strategic insights from Formula 1 data.
          </p>
        </motion.div>

        {/* Quick Stats */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="flex items-center justify-center gap-4 mb-10"
        >
          <StatBadge value="2024" label="Season" />
          <StatBadge value="24" label="Circuits" />
          <StatBadge value="20" label="Drivers" />
          <StatBadge value="10" label="Teams" />
        </motion.div>

        {/* Feature Cards */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10"
        >
          {features.map((feature, idx) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.3 + idx * 0.1 }}
            >
              <FeatureCard {...feature} />
            </motion.div>
          ))}
        </motion.div>

        {/* Suggested Prompts */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <div className="flex items-center justify-center gap-2 mb-4">
            <Zap className="w-4 h-4 text-f1-red" />
            <span className="text-sm font-medium text-text-secondary">Try asking</span>
          </div>
          <SuggestedPrompts onSelect={onSelect} />
        </motion.div>

        {/* Bottom hint */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.7 }}
          className="mt-8 text-xs text-text-muted"
        >
          Press <kbd className="px-1.5 py-0.5 rounded bg-surface text-text-secondary mx-1">Enter</kbd> to send
        </motion.p>
      </motion.div>
    </div>
  )
}

export function ChatArea({
  messages,
  isStreaming,
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
      <AnimatedBackground />

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

      {/* Input area with modern glass effect */}
      <div className="relative z-20">
        {/* Gradient fade */}
        <div className="absolute bottom-full left-0 right-0 h-24 bg-gradient-to-t from-background-primary via-background-primary/80 to-transparent pointer-events-none" />

        <div className="bg-background-primary/90 backdrop-blur-xl border-t border-white/5">
          <div className="max-w-4xl mx-auto">
            <MessageInput onSend={onSendMessage} disabled={isStreaming} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default ChatArea
