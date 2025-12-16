'use client'

import { Menu, PanelRightClose, PanelRightOpen, Radio, Zap } from 'lucide-react'
import { motion } from 'framer-motion'
import { useUIStore } from '@/stores/ui-store'

export function Header() {
  const {
    sidebarOpen,
    toggleSidebar,
    artifactPanelOpen,
    toggleArtifactPanel,
    currentArtifact,
  } = useUIStore()

  return (
    <header className="relative flex items-center justify-between px-4 py-3 bg-background-primary/80 backdrop-blur-xl border-b border-white/5">
      {/* Subtle gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-r from-f1-red/5 via-transparent to-transparent pointer-events-none" />

      <div className="relative flex items-center gap-4">
        {/* Mobile menu button */}
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={toggleSidebar}
          className="p-2 hover:bg-white/5 rounded-xl transition-colors lg:hidden"
          aria-label="Toggle sidebar"
        >
          <Menu className="w-5 h-5 text-f1-gray" />
        </motion.button>

        {/* Logo and title */}
        <div className="flex items-center gap-3">
          {/* Animated logo */}
          <motion.div
            className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-f1-red to-red-700"
            style={{
              boxShadow: '0 4px 15px rgba(225, 6, 0, 0.3)',
            }}
          >
            {/* Pulsing glow */}
            <motion.div
              className="absolute inset-0 rounded-xl bg-f1-red"
              animate={{ scale: [1, 1.1, 1], opacity: [0.3, 0, 0.3] }}
              transition={{ duration: 2, repeat: Infinity }}
            />
            <span className="relative text-xl">🏎️</span>
          </motion.div>

          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-white tracking-tight">
                F1 Race Intelligence
              </h1>
              <motion.span
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium
                         bg-gradient-to-r from-orange-500/20 to-yellow-500/20
                         text-orange-300 rounded-full border border-orange-500/30"
              >
                <Zap className="w-2.5 h-2.5" />
                BETA
              </motion.span>
            </div>
            <span className="hidden sm:block text-[10px] text-f1-gray/60 tracking-wider">
              AI-POWERED RACE ANALYSIS
            </span>
          </div>
        </div>
      </div>

      {/* Right side controls */}
      <div className="relative flex items-center gap-3">
        {/* Live indicator (decorative) */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10">
          <motion.div
            className="w-2 h-2 rounded-full bg-green-500"
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
          <span className="text-xs text-f1-gray font-medium">Connected</span>
        </div>

        {/* Artifact panel toggle */}
        {currentArtifact && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={toggleArtifactPanel}
            className="p-2.5 hover:bg-white/5 rounded-xl transition-colors border border-white/10"
            aria-label={artifactPanelOpen ? 'Hide panel' : 'Show panel'}
          >
            {artifactPanelOpen ? (
              <PanelRightClose className="w-5 h-5 text-f1-gray" />
            ) : (
              <PanelRightOpen className="w-5 h-5 text-f1-gray" />
            )}
          </motion.button>
        )}
      </div>

      {/* Bottom racing stripe */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-f1-red/50 to-transparent" />
    </header>
  )
}

export default Header
