'use client'

import { useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, MessageSquare, Trash2, X, Sparkles, History } from 'lucide-react'
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

export function Sidebar() {
  const { sessions, activeSessionId, createSession, switchSession, deleteSession } =
    useChatStore()
  const { sidebarOpen, setSidebarOpen } = useUIStore()

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

  return (
    <>
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
            className="fixed lg:relative z-30 w-[280px] h-full bg-background-primary/95 backdrop-blur-xl
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
                  className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-f1-red to-red-600
                             text-white rounded-xl transition-all text-sm font-medium
                             hover:shadow-lg hover:shadow-f1-red/20"
                  style={{
                    boxShadow: '0 4px 15px rgba(225, 6, 0, 0.2)',
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
                  <X className="w-5 h-5 text-f1-gray" />
                </motion.button>
              </div>
            </div>

            {/* Session list */}
            <div className="relative flex-1 overflow-y-auto scrollbar-thin p-3">
              {groupedSessions.length > 0 && (
                <div className="flex items-center gap-2 px-2 mb-3">
                  <History className="w-3.5 h-3.5 text-f1-gray/50" />
                  <span className="text-xs text-f1-gray/50 font-medium tracking-wider">HISTORY</span>
                </div>
              )}

              {groupedSessions.map((group) => (
                <div key={group.label} className="mb-4">
                  <h3 className="px-3 py-2 text-xs font-medium text-f1-gray/60 uppercase tracking-wider">
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
                                        ? 'bg-white/10 text-white'
                                        : 'text-f1-gray hover:bg-white/5 hover:text-white'
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
                        <motion.button
                          initial={{ opacity: 0, scale: 0.8 }}
                          whileHover={{ scale: 1.1 }}
                          onClick={(e) => {
                            e.stopPropagation()
                            deleteSession(session.id)
                          }}
                          className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-500/20
                                     rounded-lg transition-all"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-f1-gray hover:text-red-400 transition-colors" />
                        </motion.button>
                      </motion.div>
                    ))}
                  </div>
                </div>
              ))}

              {sessions.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 px-4">
                  <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
                    <MessageSquare className="w-8 h-8 text-f1-gray/30" />
                  </div>
                  <p className="text-center text-f1-gray/50 text-sm">
                    No conversations yet
                  </p>
                  <p className="text-center text-f1-gray/30 text-xs mt-1">
                    Start a new analysis above
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="relative p-4 border-t border-white/5">
              <div className="flex items-center gap-3 px-2">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-f1-red/30 to-orange-500/30 flex items-center justify-center">
                  <span className="text-sm">🏁</span>
                </div>
                <div className="flex-1">
                  <p className="text-xs text-white/80 font-medium">F1 RIA</p>
                  <p className="text-[10px] text-f1-gray/50">v1.0.0 Beta</p>
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
