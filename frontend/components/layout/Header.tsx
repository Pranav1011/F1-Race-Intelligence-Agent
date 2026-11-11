'use client'

import { Loader2, Menu, PanelRightClose, PanelRightOpen, Wifi, WifiOff } from 'lucide-react'
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
      <div className="relative flex items-center gap-4">
        {/* Mobile menu button */}
        <button
          onClick={toggleSidebar}
          className="p-2 hover:bg-white/5 rounded-xl transition-colors lg:hidden"
          aria-label={sidebarOpen ? 'Close chat history' : 'Open chat history'}
          aria-expanded={sidebarOpen}
          aria-controls="chat-sidebar"
        >
          <Menu className="w-5 h-5 text-text-muted" aria-hidden="true" />
        </button>

        {/* Logo and title */}
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center w-9 h-9 rounded-lg bg-f1-red"
            aria-hidden="true"
          >
            <span className="text-lg">🏎️</span>
          </div>

          <div className="flex flex-col">
            <h1 className="text-base font-semibold text-text-primary tracking-tight">
              F1 Race Intelligence
            </h1>
            <span className="hidden sm:block text-xs text-text-muted">
              Race analysis agent · 2018–2024 seasons
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
