'use client'

import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plus,
  MessageSquare,
  Trash2,
  X,
  Sparkles,
  History,
  AlertTriangle,
  Activity,
} from 'lucide-react'
import { useChatStore } from '@/stores/chat-store'
import { useUIStore } from '@/stores/ui-store'
import { Session } from '@/types'

function groupSessionsByDate(sessions: Session[]) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
  const lastWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)

  const groups: { label: string; sessions: Session[] }[] = [
    { label: 'Today', sessions: [] },
    { label: 'Yesterday', sessions: [] },
    { label: 'Previous 7 Days', sessions: [] },
    { label: 'Older', sessions: [] },
  ]

  sessions.forEach((session) => {
    const date = new Date(session.updatedAt)
    if (date >= today) {
      groups[0].sessions.push(session)
    } else if (date >= yesterday) {
      groups[1].sessions.push(session)
    } else if (date >= lastWeek) {
      groups[2].sessions.push(session)
    } else {
      groups[3].sessions.push(session)
    }
  })

  // Filter out empty groups
  return groups.filter((g) => g.sessions.length > 0)
}

// Confirmation dialog component (reusable for both single and all deletion)
function DeleteConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  isOpen: boolean
  title: string
  message: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!isOpen) return null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onCancel}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-background-secondary border border-white/10 rounded-2xl p-6 max-w-sm mx-4 shadow-2xl"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-data-negative/10 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-data-negative" />
          </div>
          <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
        </div>
        <p className="text-text-secondary text-sm mb-6">
          {message}
        </p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2.5 rounded-xl bg-surface hover:bg-surface-hover
                       text-text-primary font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 px-4 py-2.5 rounded-xl bg-data-negative hover:bg-data-negative/80
                       text-white font-medium transition-colors"
          >
            {confirmLabel}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}

export function Sidebar() {
  const { sessions, activeSessionId, createSession, switchSession, deleteSession, clearAllSessions } =
    useChatStore()
  const { sidebarOpen, setSidebarOpen } = useUIStore()
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; title: string } | null>(null)

  const groupedSessions = useMemo(
    () => groupSessionsByDate([...sessions].sort((a, b) =>
      new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    )),
    [sessions]
  )

  const handleNewChat = () => {
    createSession()
    // Close sidebar on mobile after creating
    if (window.innerWidth < 1024) {
      setSidebarOpen(false)
    }
  }

  const handleSelectSession = (id: string) => {
    switchSession(id)
    // Close sidebar on mobile after selecting
    if (window.innerWidth < 1024) {
      setSidebarOpen(false)
    }
  }

  const handleClearAll = () => {
    setShowClearConfirm(true)
  }

  const confirmClearAll = () => {
    clearAllSessions()
    setShowClearConfirm(false)
  }

  const handleDeleteChat = (id: string, title: string) => {
    setDeleteConfirm({ id, title })
  }

  const confirmDeleteChat = () => {
    if (deleteConfirm) {
      deleteSession(deleteConfirm.id)
      setDeleteConfirm(null)
    }
  }

  return (
    <>
      {/* Clear all confirmation dialog */}
      <AnimatePresence>
        {showClearConfirm && (
          <DeleteConfirmDialog
            isOpen={showClearConfirm}
            title="Clear All History?"
            message="This will permanently delete all your chat sessions. This action cannot be undone."
            confirmLabel="Delete All"
            onConfirm={confirmClearAll}
            onCancel={() => setShowClearConfirm(false)}
          />
        )}
      </AnimatePresence>

      {/* Single chat deletion confirmation dialog */}
      <AnimatePresence>
        {deleteConfirm && (
          <DeleteConfirmDialog
            isOpen={!!deleteConfirm}
            title="Delete Chat?"
            message={`Are you sure you want to delete "${deleteConfirm.title}"? This action cannot be undone.`}
            confirmLabel="Delete"
            onConfirm={confirmDeleteChat}
            onCancel={() => setDeleteConfirm(null)}
          />
        )}
      </AnimatePresence>

      {/* Overlay for mobile */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-20 lg:hidden"
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.aside
            initial={{ x: -280 }}
            animate={{ x: 0 }}
            exit={{ x: -280 }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed lg:relative z-30 w-[280px] h-full bg-background-secondary/95 backdrop-blur-xl
                       border-r border-white/5 flex flex-col"
          >
            {/* Decorative gradient */}
            <div className="absolute inset-0 bg-gradient-to-b from-f1-red/5 via-transparent to-transparent pointer-events-none" />

            {/* Header */}
            <div className="relative p-4 border-b border-white/5">
              <div className="flex items-center justify-between">
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleNewChat}
                  className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-f1-red to-f1-redLight
                             text-white rounded-xl transition-all text-sm font-medium
                             hover:shadow-lg hover:shadow-f1-red/20"
                  style={{
                    boxShadow: '0 4px 15px rgba(227, 25, 55, 0.2)',
                  }}
                >
                  <Sparkles className="w-4 h-4" />
                  New Analysis
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={() => setSidebarOpen(false)}
                  className="p-2 hover:bg-white/5 rounded-lg transition-colors lg:hidden"
                >
                  <X className="w-5 h-5 text-text-muted" />
                </motion.button>
              </div>
            </div>

            {/* Session list */}
            <div className="relative flex-1 overflow-y-auto scrollbar-thin p-3">
              {groupedSessions.length > 0 && (
                <div className="flex items-center justify-between px-2 mb-3">
                  <div className="flex items-center gap-2">
                    <History className="w-3.5 h-3.5 text-text-muted" />
                    <span className="text-xs text-text-muted font-medium tracking-wider">HISTORY</span>
                  </div>
                  {sessions.length > 0 && (
                    <motion.button
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={handleClearAll}
                      className="text-xs text-text-muted hover:text-data-negative transition-colors
                                 flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-data-negative/10"
                    >
                      <Trash2 className="w-3 h-3" />
                      Clear All
                    </motion.button>
                  )}
                </div>
              )}

              {groupedSessions.map((group) => (
                <div key={group.label} className="mb-4">
                  <h3 className="px-3 py-2 text-xs font-medium text-text-muted uppercase tracking-wider">
                    {group.label}
                  </h3>
                  <div className="space-y-1">
                    {group.sessions.map((session) => (
                      <motion.div
                        key={session.id}
                        whileHover={{ x: 4 }}
                        className={`group relative flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer
                                    transition-all duration-200 ${
                                      session.id === activeSessionId
                                        ? 'bg-surface-active text-text-primary'
                                        : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
                                    }`}
                        onClick={() => handleSelectSession(session.id)}
                      >
                        {/* Active indicator */}
                        {session.id === activeSessionId && (
                          <motion.div
                            layoutId="activeSession"
                            className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-f1-red rounded-full"
                          />
                        )}

                        <MessageSquare className="w-4 h-4 flex-shrink-0" />
                        <span className="flex-1 truncate text-sm">
                          {session.title}
                        </span>
                        {/* Always visible delete button */}
                        <motion.button
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleDeleteChat(session.id, session.title)
                          }}
                          className="p-1.5 hover:bg-data-negative/20 rounded-lg transition-all
                                     opacity-60 hover:opacity-100"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-text-muted hover:text-data-negative transition-colors" />
                        </motion.button>
                      </motion.div>
                    ))}
                  </div>
                </div>
              ))}

              {sessions.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 px-4">
                  <div className="w-16 h-16 rounded-2xl bg-surface flex items-center justify-center mb-4">
                    <MessageSquare className="w-8 h-8 text-text-muted/30" />
                  </div>
                  <p className="text-center text-text-muted text-sm">
                    No conversations yet
                  </p>
                  <p className="text-center text-text-muted/50 text-xs mt-1">
                    Start a new analysis above
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="relative p-4 border-t border-white/5">
              <div className="flex items-center gap-3 px-2">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-f1-red/30 to-accent-orange/30
                                flex items-center justify-center border border-white/5">
                  <Activity className="w-4 h-4 text-f1-red" />
                </div>
                <div className="flex-1">
                  <p className="text-sm text-text-primary font-medium">F1 RIA</p>
                  <p className="text-[10px] text-text-muted">Race Intelligence Assistant</p>
                </div>
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}

export default Sidebar
