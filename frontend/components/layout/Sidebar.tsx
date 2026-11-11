'use client'

import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, MessageSquare, Trash2, X, History, AlertTriangle } from 'lucide-react'
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
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
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
            className="flex-1 px-4 py-2.5 rounded-xl bg-f1-redDark hover:bg-f1-red
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

      {/* Sidebar: a drawer below lg (closed by default), always shown from lg up */}
      <aside
        id="chat-sidebar"
        aria-label="Chat history"
        className={`fixed lg:relative z-30 w-[280px] h-full bg-background-secondary
                    border-r border-white/5 flex flex-col shrink-0
                    transition-[transform,visibility] duration-300 ease-out
                    lg:visible lg:translate-x-0 ${
                      sidebarOpen ? 'visible translate-x-0' : 'invisible -translate-x-full'
                    }`}
      >
        {/* Header */}
        <div className="relative p-4 border-b border-white/5">
          <div className="flex items-center justify-between">
            <button
              onClick={handleNewChat}
              className="flex items-center gap-2 px-4 py-2.5 bg-f1-red hover:bg-f1-redDark
                         text-white rounded-xl transition-colors text-sm font-medium"
            >
              <Plus className="w-4 h-4" aria-hidden="true" />
              New analysis
            </button>
            <button
              onClick={() => setSidebarOpen(false)}
              className="p-2 hover:bg-white/5 rounded-lg transition-colors lg:hidden"
              aria-label="Close chat history"
            >
              <X className="w-5 h-5 text-text-muted" aria-hidden="true" />
            </button>
          </div>
        </div>

        {/* Session list */}
        <div className="relative flex-1 overflow-y-auto scrollbar-thin p-3">
          {groupedSessions.length > 0 && (
            <div className="flex items-center justify-between px-2 mb-3">
              <div className="flex items-center gap-2">
                <History className="w-3.5 h-3.5 text-text-muted" aria-hidden="true" />
                <span className="text-xs text-text-muted font-medium tracking-wider">HISTORY</span>
              </div>
              {sessions.length > 0 && (
                <button
                  onClick={handleClearAll}
                  className="text-xs text-text-muted hover:text-data-negative transition-colors
                             flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-data-negative/10"
                >
                  <Trash2 className="w-3 h-3" aria-hidden="true" />
                  Clear all
                </button>
              )}
            </div>
          )}

          {groupedSessions.map((group) => (
            <div key={group.label} className="mb-4">
              <h3 className="px-3 py-2 text-xs font-medium text-text-muted uppercase tracking-wider">
                {group.label}
              </h3>
              <ul className="space-y-1">
                {group.sessions.map((session) => {
                  const isActive = session.id === activeSessionId
                  return (
                    <li
                      key={session.id}
                      className={`group relative flex items-center rounded-xl transition-colors duration-200 ${
                        isActive
                          ? 'bg-surface-active text-text-primary'
                          : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
                      }`}
                    >
                      {/* Active indicator */}
                      {isActive && (
                        <motion.div
                          layoutId="activeSession"
                          className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-f1-red rounded-full"
                        />
                      )}

                      <button
                        onClick={() => handleSelectSession(session.id)}
                        aria-current={isActive ? 'page' : undefined}
                        className="flex flex-1 min-w-0 items-center gap-3 pl-3 py-2.5 text-left rounded-xl"
                      >
                        <MessageSquare className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                        <span className="flex-1 truncate text-sm">{session.title}</span>
                      </button>
                      <button
                        onClick={() => handleDeleteChat(session.id, session.title)}
                        className="mr-2 p-1.5 hover:bg-data-negative/20 rounded-lg transition-colors
                                   text-text-muted hover:text-data-negative"
                        aria-label={`Delete chat "${session.title}"`}
                      >
                        <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}

          {sessions.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 px-4">
              <p className="text-center text-text-secondary text-sm">No conversations yet</p>
              <p className="text-center text-text-muted text-xs mt-1">
                Start a new analysis above
              </p>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}

export default Sidebar
