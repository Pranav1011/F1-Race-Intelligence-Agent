'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface StatusIndicatorProps {
  message: string | null
  isActive: boolean
}

// F1 pit wall radio themed status icons
const STATUS_ICONS: Record<string, string> = {
  understanding: '🎧',
  planning: '📊',
  executing: '🏎️',
  processing: '🔥',
  evaluating: '📦',
  enriching: '🧠',
  generating: '⚡',
  validating: '🏁',
  default: '📻',
}

// Radio crackle effect simulation
const RadioWave = () => (
  <div className="flex items-center gap-0.5">
    {[...Array(5)].map((_, i) => (
      <motion.div
        key={i}
        className="w-0.5 bg-accent-emerald rounded-full"
        animate={{
          height: [4, 12, 4, 16, 4],
          opacity: [0.5, 1, 0.5, 1, 0.5],
        }}
        transition={{
          duration: 0.8,
          repeat: Infinity,
          delay: i * 0.1,
          ease: 'easeInOut',
        }}
      />
    ))}
  </div>
)

export function StatusIndicator({ message, isActive }: StatusIndicatorProps) {
  const [displayMessage, setDisplayMessage] = useState(message)
  const [key, setKey] = useState(0)

  // Extract stage from message for icon - matches F1 pit wall radio messages
  const getIcon = () => {
    if (!message) return STATUS_ICONS.default
    const lower = message.toLowerCase()
    if (lower.includes('checking') || lower.includes('copy')) return '🎧'
    if (lower.includes('strategy') || lower.includes('plan')) return '📊'
    if (lower.includes('braking') || lower.includes('data')) return '🏎️'
    if (lower.includes('overtaking') || lower.includes('outside')) return '🔥'
    if (lower.includes('box') || lower.includes('getting to you')) return '📦'
    if (lower.includes('context') || lower.includes('focused')) return '🧠'
    if (lower.includes('hammer') || lower.includes('composing')) return '⚡'
    if (lower.includes('final') || lower.includes('p1')) return '🏁'
    return STATUS_ICONS.default
  }

  useEffect(() => {
    if (message !== displayMessage) {
      setKey((prev) => prev + 1)
      setDisplayMessage(message)
    }
  }, [message, displayMessage])

  if (!isActive || !message) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="flex justify-start mb-4"
    >
      <div className="relative">
        {/* Main container with F1 radio aesthetic */}
        <div
          className="relative overflow-hidden rounded-2xl rounded-bl-md"
          style={{
            background: 'linear-gradient(135deg, rgba(22, 22, 30, 0.95) 0%, rgba(18, 18, 26, 0.95) 100%)',
            border: '1px solid rgba(16, 185, 129, 0.2)',
            boxShadow: '0 0 20px rgba(16, 185, 129, 0.1), inset 0 0 30px rgba(0, 0, 0, 0.3)',
          }}
        >
          {/* Animated border glow */}
          <motion.div
            className="absolute inset-0 rounded-2xl"
            style={{
              border: '1px solid transparent',
              background: 'linear-gradient(90deg, transparent, rgba(16, 185, 129, 0.3), transparent)',
              backgroundSize: '200% 100%',
            }}
            animate={{
              backgroundPosition: ['200% 0%', '-200% 0%'],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: 'linear',
            }}
          />

          <div className="relative px-5 py-4">
            {/* Header - Radio channel indicator */}
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-white/10">
              <div className="flex items-center gap-1.5">
                <motion.div
                  className="w-2 h-2 rounded-full bg-accent-emerald"
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                />
                <span className="text-accent-emerald text-xs font-mono uppercase tracking-wider">
                  PITWALL RADIO
                </span>
              </div>
              <RadioWave />
            </div>

            {/* Status message */}
            <div className="flex items-center gap-3">
              <motion.span
                className="text-2xl"
                animate={{ scale: [1, 1.1, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                {getIcon()}
              </motion.span>

              <AnimatePresence mode="wait">
                <motion.div
                  key={key}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.3 }}
                  className="flex-1"
                >
                  <p className="text-text-primary font-medium text-sm">
                    {message}
                  </p>
                </motion.div>
              </AnimatePresence>
            </div>

            {/* Loading bar at bottom */}
            <div className="mt-3 h-1 bg-white/10 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-accent-emerald/50 via-accent-emerald to-accent-emerald/50"
                animate={{
                  x: ['-100%', '100%'],
                }}
                transition={{
                  duration: 1.5,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }}
                style={{ width: '50%' }}
              />
            </div>
          </div>
        </div>

        {/* Decorative elements */}
        <div className="absolute -right-1 top-1/2 -translate-y-1/2 w-1 h-8 bg-gradient-to-b from-transparent via-accent-emerald/50 to-transparent rounded-full" />
      </div>
    </motion.div>
  )
}

export default StatusIndicator
