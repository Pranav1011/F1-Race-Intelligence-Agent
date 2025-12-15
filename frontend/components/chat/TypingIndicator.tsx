'use client'

import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

// Query type categories for context-aware messages
type QueryContext =
  | 'comparison'
  | 'strategy'
  | 'pace'
  | 'telemetry'
  | 'results'
  | 'general'

interface TypingIndicatorProps {
  queryContext?: QueryContext
  toolInProgress?: string
}

// F1-themed thinking messages by context
const THINKING_MESSAGES: Record<QueryContext, string[]> = {
  comparison: [
    'Comparing lap times...',
    'Analyzing sector deltas...',
    'Running head-to-head analysis...',
    'Checking consistency data...',
    'Measuring pace differential...',
  ],
  strategy: [
    'Consulting the pit wall...',
    'Analyzing tire degradation curves...',
    'Running strategy simulations...',
    'Checking optimal pit windows...',
    'Modeling undercut scenarios...',
    'Calculating stint lengths...',
  ],
  pace: [
    'Crunching lap time data...',
    'Analyzing race pace...',
    'Checking for traffic impact...',
    'Measuring fuel-corrected pace...',
    'Reviewing stint performance...',
  ],
  telemetry: [
    'Processing telemetry streams...',
    'Analyzing throttle traces...',
    'Checking brake application points...',
    'Reviewing gear shift patterns...',
    'Measuring speed through sectors...',
  ],
  results: [
    'Fetching race results...',
    'Compiling championship standings...',
    'Calculating points distribution...',
    'Reviewing finishing positions...',
  ],
  general: [
    'Discussing with the race engineer...',
    'Reviewing timing screens...',
    'Checking the data...',
    'Analyzing the session...',
    'Running the numbers...',
    'Box, box, thinking...',
    'Warming up the data...',
    'Full send on analysis...',
    'Lights out, processing...',
  ],
}

// Fun rotating messages (used occasionally)
const FUN_MESSAGES = [
  'Getting in the zone...',
  "Smooth operator processing...",
  'Maximum attack on your query...',
  'No Michael, no, this is so right...',
  'And we are live...',
  'Pedal to the metal...',
  'DRS enabled, going faster...',
  'Push push push...',
  'Hammertime on the analysis...',
]

// Tool-specific messages
const TOOL_MESSAGES: Record<string, string[]> = {
  get_lap_times: ['Fetching lap times from timing...', 'Loading lap data...'],
  get_head_to_head: ['Running head-to-head comparison...', 'Comparing drivers...'],
  get_stint_analysis: ['Analyzing stint performance...', 'Checking tire stints...'],
  get_season_standings: ['Loading championship standings...', 'Fetching points data...'],
  get_race_summary: ['Getting race summary...', 'Loading race statistics...'],
  search_f1_knowledge: ['Searching knowledge base...', 'Consulting F1 archives...'],
  get_driver_info: ['Looking up driver information...', 'Checking driver profile...'],
}

export function TypingIndicator({
  queryContext = 'general',
  toolInProgress,
}: TypingIndicatorProps) {
  const [messageIndex, setMessageIndex] = useState(0)
  const [showFunMessage, setShowFunMessage] = useState(false)

  // Get appropriate messages based on context
  const messages = useMemo(() => {
    // If a tool is in progress, use tool-specific messages
    if (toolInProgress && TOOL_MESSAGES[toolInProgress]) {
      return TOOL_MESSAGES[toolInProgress]
    }
    // Otherwise use context-based messages
    return THINKING_MESSAGES[queryContext] || THINKING_MESSAGES.general
  }, [queryContext, toolInProgress])

  // Rotate through messages
  useEffect(() => {
    const interval = setInterval(() => {
      // 10% chance to show a fun message
      if (Math.random() < 0.1 && !showFunMessage) {
        setShowFunMessage(true)
        setMessageIndex(Math.floor(Math.random() * FUN_MESSAGES.length))
      } else {
        setShowFunMessage(false)
        setMessageIndex((prev) => (prev + 1) % messages.length)
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [messages.length, showFunMessage])

  const currentMessage = showFunMessage
    ? FUN_MESSAGES[messageIndex % FUN_MESSAGES.length]
    : messages[messageIndex % messages.length]

  return (
    <div className="flex justify-start mb-4">
      <div className="bg-bg-secondary rounded-2xl rounded-bl-md px-4 py-3">
        <div className="flex items-center gap-3">
          {/* F1-style loading animation */}
          <div className="flex items-center gap-1">
            {[0, 1, 2, 3, 4].map((i) => (
              <motion.div
                key={i}
                className="w-1 h-4 bg-f1-red rounded-full"
                animate={{
                  scaleY: [0.3, 1, 0.3],
                  opacity: [0.3, 1, 0.3],
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

          {/* Thinking message */}
          <AnimatePresence mode="wait">
            <motion.span
              key={currentMessage}
              className="text-sm text-f1-gray"
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.2 }}
            >
              {currentMessage}
            </motion.span>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}

// Simple version without context (backwards compatible)
export function SimpleTypingIndicator() {
  return <TypingIndicator queryContext="general" />
}
