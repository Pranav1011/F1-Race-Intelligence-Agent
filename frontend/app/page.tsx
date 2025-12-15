'use client'

import { useEffect, useCallback } from 'react'
import { useChatStore } from '@/stores/chat-store'
import { useUIStore } from '@/stores/ui-store'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { ArtifactPanel } from '@/components/layout/ArtifactPanel'
import { ChatArea } from '@/components/chat/ChatArea'
import { API_ENDPOINTS } from '@/utils/api'

export default function Home() {
  const {
    activeSessionId,
    getMessages,
    isStreaming,
    createSession,
    addMessage,
    appendToLastMessage,
    updateLastMessage,
    setStreaming,
    loadFromStorage,
  } = useChatStore()

  const { setArtifact, sidebarOpen } = useUIStore()

  // Load sessions from localStorage on mount
  useEffect(() => {
    loadFromStorage()
  }, [loadFromStorage])

  // WebSocket connection
  const { sendMessage: wsSendMessage } = useWebSocket({
    url: API_ENDPOINTS.chatWs,
    onToken: (token) => {
      appendToLastMessage(token)
    },
    onVisualization: (viz) => {
      setArtifact(viz)
      updateLastMessage({ visualization: viz })
    },
    onMetadata: (meta) => {
      updateLastMessage({ metadata: meta })
    },
    onDone: () => {
      setStreaming(false)
    },
    onError: (error) => {
      setStreaming(false)
      appendToLastMessage(`\n\nError: ${error}`)
    },
  })

  // Handle sending a message
  const handleSendMessage = useCallback(
    (content: string) => {
      // Ensure we have an active session
      let sessionId = activeSessionId
      if (!sessionId) {
        sessionId = createSession()
      }

      // Add user message
      addMessage({ role: 'user', content })

      // Add empty assistant message placeholder
      addMessage({ role: 'assistant', content: '' })

      // Start streaming
      setStreaming(true)

      // Send via WebSocket
      wsSendMessage(content, sessionId)
    },
    [activeSessionId, createSession, addMessage, setStreaming, wsSendMessage]
  )

  const messages = getMessages()

  return (
    <div className="flex h-screen bg-bg-primary text-white overflow-hidden">
      {/* Sidebar */}
      <Sidebar />

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <Header />

        {/* Chat + Artifact Panel */}
        <div className="flex-1 flex overflow-hidden">
          {/* Chat area */}
          <main className="flex-1 min-w-0">
            <ChatArea
              messages={messages}
              isStreaming={isStreaming}
              onSendMessage={handleSendMessage}
            />
          </main>

          {/* Artifact Panel */}
          <ArtifactPanel />
        </div>
      </div>
    </div>
  )
}
