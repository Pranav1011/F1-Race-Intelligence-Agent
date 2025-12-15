'use client'

import { useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, MessageSquare, Trash2, X } from 'lucide-react'
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
            className="fixed inset-0 bg-black/50 z-20 lg:hidden"
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
            className="fixed lg:relative z-30 w-[280px] h-full bg-bg-primary border-r border-white/10 flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <button
                onClick={handleNewChat}
                className="flex items-center gap-2 px-3 py-2 bg-f1-red text-white rounded-lg
                           hover:bg-f1-red/90 transition-colors text-sm font-medium"
              >
                <Plus className="w-4 h-4" />
                New Chat
              </button>
              <button
                onClick={() => setSidebarOpen(false)}
                className="p-2 hover:bg-bg-secondary rounded-lg transition-colors lg:hidden"
              >
                <X className="w-5 h-5 text-f1-gray" />
              </button>
            </div>

            {/* Session list */}
            <div className="flex-1 overflow-y-auto scrollbar-thin p-2">
              {groupedSessions.map((group) => (
                <div key={group.label} className="mb-4">
                  <h3 className="px-3 py-2 text-xs font-medium text-f1-gray uppercase tracking-wider">
                    {group.label}
                  </h3>
                  <div className="space-y-1">
                    {group.sessions.map((session) => (
                      <div
                        key={session.id}
                        className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer
                                    transition-colors ${
                                      session.id === activeSessionId
                                        ? 'bg-bg-secondary text-white'
                                        : 'text-f1-gray hover:bg-bg-secondary hover:text-white'
                                    }`}
                        onClick={() => handleSelectSession(session.id)}
                      >
                        <MessageSquare className="w-4 h-4 flex-shrink-0" />
                        <span className="flex-1 truncate text-sm">
                          {session.title}
                        </span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            deleteSession(session.id)
                          }}
                          className="opacity-0 group-hover:opacity-100 p-1 hover:bg-bg-tertiary
                                     rounded transition-opacity"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-f1-gray hover:text-f1-red" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {sessions.length === 0 && (
                <p className="text-center text-f1-gray text-sm py-8">
                  No conversations yet
                </p>
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}
