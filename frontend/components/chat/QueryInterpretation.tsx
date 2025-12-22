'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, AlertCircle, ArrowRight, CheckCircle2 } from 'lucide-react'
import { QueryInterpretation as QueryInterpretationType } from '@/types'

interface QueryInterpretationProps {
  interpretation: QueryInterpretationType | null
  isVisible: boolean
}

export function QueryInterpretation({ interpretation, isVisible }: QueryInterpretationProps) {
  if (!interpretation) return null

  const hasCorrections = interpretation.corrections.length > 0
  const wasExpanded = interpretation.expanded !== interpretation.original

  // Don't show if nothing interesting happened
  if (!hasCorrections && !wasExpanded) return null

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: -10, height: 0 }}
          animate={{ opacity: 1, y: 0, height: 'auto' }}
          exit={{ opacity: 0, y: -10, height: 0 }}
          transition={{ duration: 0.3 }}
          className="mx-4 mb-3 overflow-hidden"
        >
          <div className="bg-surface/50 border border-white/5 rounded-xl px-4 py-3 backdrop-blur-sm">
            {/* Typo corrections */}
            {hasCorrections && (
              <div className="flex items-start gap-2 mb-2">
                <CheckCircle2 className="w-4 h-4 text-data-positive mt-0.5 flex-shrink-0" />
                <div className="text-sm">
                  <span className="text-text-muted">Auto-corrected: </span>
                  {interpretation.corrections.map((c, i) => (
                    <span key={i} className="inline-flex items-center gap-1">
                      <span className="text-data-negative/70 line-through">{c.original}</span>
                      <ArrowRight className="w-3 h-3 text-text-muted/50" />
                      <span className="text-data-positive">{c.corrected}</span>
                      {i < interpretation.corrections.length - 1 && (
                        <span className="text-text-muted/50 mx-1">•</span>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Query expansion */}
            {wasExpanded && (
              <div className="flex items-start gap-2">
                <Sparkles className="w-4 h-4 text-data-warning mt-0.5 flex-shrink-0" />
                <div className="text-sm">
                  <span className="text-text-muted">Understood as: </span>
                  <span className="text-text-primary/90">{interpretation.expanded}</span>
                </div>
              </div>
            )}

            {/* Intent badge */}
            <div className="flex items-center gap-2 mt-2 pt-2 border-t border-white/5">
              <span className="text-xs text-text-muted/70">Intent:</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${getIntentColor(interpretation.intent)}`}>
                {formatIntent(interpretation.intent)}
              </span>
              <span className="text-xs text-text-muted/60">
                ({Math.round(interpretation.confidence * 100)}% confidence)
              </span>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function getIntentColor(intent: string): string {
  const colors: Record<string, string> = {
    standings: 'bg-blue-500/20 text-blue-300',
    race_results: 'bg-green-500/20 text-green-300',
    comparison: 'bg-purple-500/20 text-purple-300',
    lap_times: 'bg-amber-500/20 text-amber-300',
    pit_stops: 'bg-orange-500/20 text-orange-300',
    tire_strategy: 'bg-pink-500/20 text-pink-300',
    qualifying: 'bg-cyan-500/20 text-cyan-300',
    overtaking: 'bg-red-500/20 text-red-300',
    reliability: 'bg-gray-500/20 text-gray-300',
    weather: 'bg-sky-500/20 text-sky-300',
    general: 'bg-white/10 text-white/70',
  }
  return colors[intent] || colors.general
}

function formatIntent(intent: string): string {
  const labels: Record<string, string> = {
    standings: 'Championship',
    race_results: 'Race Results',
    comparison: 'Comparison',
    lap_times: 'Lap Analysis',
    pit_stops: 'Pit Strategy',
    tire_strategy: 'Tire Strategy',
    qualifying: 'Qualifying',
    overtaking: 'Overtaking',
    reliability: 'Reliability',
    weather: 'Weather',
    team_performance: 'Team Performance',
    career_stats: 'Career Stats',
    track_specific: 'Track Analysis',
    trend: 'Trend Analysis',
    general: 'General',
  }
  return labels[intent] || intent.replace(/_/g, ' ')
}

export default QueryInterpretation
