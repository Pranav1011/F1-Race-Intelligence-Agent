'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { X, Maximize2, Minimize2 } from 'lucide-react'
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
          className={`h-full bg-bg-primary border-l border-white/10 flex flex-col overflow-hidden
                      ${isFullscreen ? 'fixed inset-0 z-50' : 'relative'}`}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <span className="text-lg">📊</span>
              <h3 className="text-sm font-medium text-white truncate">
                {currentArtifact.title || 'Visualization'}
              </h3>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setIsFullscreen(!isFullscreen)}
                className="p-2 hover:bg-bg-secondary rounded-lg transition-colors"
                aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
              >
                {isFullscreen ? (
                  <Minimize2 className="w-4 h-4 text-f1-gray" />
                ) : (
                  <Maximize2 className="w-4 h-4 text-f1-gray" />
                )}
              </button>
              <button
                onClick={handleClose}
                className="p-2 hover:bg-bg-secondary rounded-lg transition-colors"
                aria-label="Close panel"
              >
                <X className="w-4 h-4 text-f1-gray" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-auto p-4">
            <ChartRenderer visualization={currentArtifact} />
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
