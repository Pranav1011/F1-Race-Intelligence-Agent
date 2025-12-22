'use client'

import { useEffect, useCallback, useState } from 'react'
import { useChatStore } from '@/stores/chat-store'
import { useUIStore } from '@/stores/ui-store'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { ArtifactPanel } from '@/components/layout/ArtifactPanel'
import { ChatArea } from '@/components/chat/ChatArea'
import { API_ENDPOINTS } from '@/utils/api'
import { QueryInterpretation as QueryInterpretationType } from '@/types'

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

  // Track current status message for loading indicator
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [statusDetail, setStatusDetail] = useState<string | null>(null)
  const [statusProgress, setStatusProgress] = useState<number | null>(null)

  // Track query interpretation for feedback display
  const [interpretation, setInterpretation] = useState<QueryInterpretationType | null>(null)
  const [showInterpretation, setShowInterpretation] = useState(false)

  // Load sessions from localStorage on mount
  useEffect(() => {
    loadFromStorage()
  }, [loadFromStorage])

  // WebSocket connection
  const { sendMessage: wsSendMessage } = useWebSocket({
    url: API_ENDPOINTS.chatWs,
    onInterpreted: (interp) => {
      // Show interpretation feedback if there are corrections or expansion
      setInterpretation(interp)
      setShowInterpretation(true)
      // Auto-hide after 5 seconds
      setTimeout(() => setShowInterpretation(false), 5000)
    },
    onToken: (token) => {
      // Clear status message when we start receiving tokens
      setStatusMessage(null)
      setStatusDetail(null)
      setStatusProgress(null)
      appendToLastMessage(token)
    },
    onVisualization: (viz) => {
      setArtifact(viz)
      updateLastMessage({ visualization: viz })
    },
    onMetadata: (meta) => {
      updateLastMessage({ metadata: meta })
    },
    onStatus: (status) => {
      // Update status message for loading indicator
      setStatusMessage(status.message)
      setStatusDetail(status.detail || null)
      setStatusProgress(status.progress || null)
    },
    onDone: () => {
      setStreaming(false)
      setStatusMessage(null)
      setStatusDetail(null)
      setStatusProgress(null)
    },
    onError: (error) => {
      setStreaming(false)
      setStatusMessage(null)
      setStatusDetail(null)
      setStatusProgress(null)
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

      // Reset interpretation state
      setInterpretation(null)
      setShowInterpretation(false)

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
    <div className="flex h-screen bg-background-primary text-text-primary overflow-hidden">
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
              statusMessage={statusMessage}
              interpretation={interpretation}
              showInterpretation={showInterpretation}
            />
          </main>

          {/* Artifact Panel */}
          <ArtifactPanel />
        </div>
      </div>
    </div>
  )
}
