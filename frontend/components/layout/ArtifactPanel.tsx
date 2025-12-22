'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { X, Maximize2, Minimize2, BarChart3 } from 'lucide-react'
import { useState } from 'react'
import { useUIStore } from '@/stores/ui-store'
import { ChartRenderer } from '@/components/visualizations/ChartRenderer'

export function ArtifactPanel() {
  const { artifactPanelOpen, currentArtifact, setArtifactPanelOpen, clearArtifact } =
    useUIStore()
  const [isFullscreen, setIsFullscreen] = useState(false)

  const handleClose = () => {
    setArtifactPanelOpen(false)
  }

  return (
    <AnimatePresence>
      {artifactPanelOpen && currentArtifact && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{
            width: isFullscreen ? '100%' : 'min(50%, 600px)',
            opacity: 1,
          }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className={`h-full bg-background-primary border-l border-white/5 flex flex-col overflow-hidden
                      ${isFullscreen ? 'fixed inset-0 z-50' : 'relative'}`}
        >
          {/* Decorative gradient */}
          <div className="absolute inset-0 bg-gradient-to-br from-accent-purple/5 via-transparent to-accent-blue/5 pointer-events-none" />

          {/* Header */}
          <div className="relative flex items-center justify-between px-4 py-3 border-b border-white/5 bg-surface/30">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-purple/20 to-accent-blue/20
                              flex items-center justify-center border border-white/5">
                <BarChart3 className="w-4 h-4 text-accent-blue" />
              </div>
              <div>
                <h3 className="text-sm font-medium text-text-primary truncate">
                  {currentArtifact.title || 'Visualization'}
                </h3>
                <p className="text-xs text-text-muted">Interactive Chart</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setIsFullscreen(!isFullscreen)}
                className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
                aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
              >
                {isFullscreen ? (
                  <Minimize2 className="w-4 h-4 text-text-muted" />
                ) : (
                  <Maximize2 className="w-4 h-4 text-text-muted" />
                )}
              </button>
              <button
                onClick={handleClose}
                className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
                aria-label="Close panel"
              >
                <X className="w-4 h-4 text-text-muted" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="relative flex-1 overflow-auto p-4">
            <div className="h-full min-h-[300px]">
              <ChartRenderer visualization={currentArtifact} />
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
