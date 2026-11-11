'use client'

import { Loader2, Menu, PanelRightClose, PanelRightOpen, Wifi, WifiOff, Zap } from 'lucide-react'
import { motion } from 'framer-motion'
import { useUIStore } from '@/stores/ui-store'
import { ConnectionStatus, useChatStore } from '@/stores/chat-store'

const CONNECTION_BADGE: Record<
  ConnectionStatus,
  { label: string; icon: typeof Wifi; className: string; iconClassName: string }
> = {
  connected: {
    label: 'Connected',
    icon: Wifi,
    className: 'border-white/5 text-text-secondary',
    iconClassName: 'text-data-positive',
  },
  disconnected: {
    label: 'Disconnected',
    icon: WifiOff,
    className: 'border-data-negative/40 text-data-negative',
    iconClassName: 'text-data-negative',
  },
  unknown: {
    label: 'Connecting',
    icon: Loader2,
    className: 'border-white/5 text-text-muted',
    iconClassName: 'text-text-muted animate-spin',
  },
}

function ConnectionBadge() {
  const connection = useChatStore((s) => s.connection)
  const badge = CONNECTION_BADGE[connection]
  const Icon = badge.icon

  return (
    <div
      role="status"
      aria-live="polite"
      data-connection={connection}
      className={`hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface border ${badge.className}`}
    >
      <Icon className={`w-3.5 h-3.5 ${badge.iconClassName}`} aria-hidden="true" />
      <span className="text-xs font-medium">{badge.label}</span>
    </div>
  )
}

export function Header() {
  const {
    sidebarOpen,
    toggleSidebar,
    artifactPanelOpen,
    toggleArtifactPanel,
    currentArtifact,
  } = useUIStore()

  return (
    <header className="relative flex items-center justify-between px-4 py-3 bg-background-primary/90 backdrop-blur-xl border-b border-white/5">
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
          <Menu className="w-5 h-5 text-text-muted" />
        </motion.button>

        {/* Logo and title */}
        <div className="flex items-center gap-3">
          {/* Animated logo */}
          <motion.div
            className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-f1-red to-f1-redDark"
            style={{
              boxShadow: '0 4px 15px rgba(227, 25, 55, 0.3)',
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
              <h1 className="text-lg font-bold text-text-primary tracking-tight">
                F1 Race Intelligence
              </h1>
              <motion.span
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium
                         bg-gradient-to-r from-accent-orange/20 to-data-warning/20
                         text-accent-orange rounded-full border border-accent-orange/30"
              >
                <Zap className="w-2.5 h-2.5" />
                BETA
              </motion.span>
            </div>
            <span className="hidden sm:block text-[10px] text-text-muted tracking-wider">
              AI-POWERED RACE ANALYSIS
            </span>
          </div>
        </div>
      </div>

      {/* Right side controls */}
      <div className="relative flex items-center gap-3">
        <ConnectionBadge />

        {/* Artifact panel toggle */}
        {currentArtifact && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={toggleArtifactPanel}
            className="p-2.5 hover:bg-white/5 rounded-xl transition-colors border border-white/5"
            aria-label={artifactPanelOpen ? 'Hide panel' : 'Show panel'}
          >
            {artifactPanelOpen ? (
              <PanelRightClose className="w-5 h-5 text-text-muted" />
            ) : (
              <PanelRightOpen className="w-5 h-5 text-text-muted" />
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
