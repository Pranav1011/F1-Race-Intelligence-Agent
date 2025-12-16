'use client'

import { useCallback, useRef, useState } from 'react'
import { WSIncomingMessage, WSOutgoingMessage, Visualization, MessageMetadata } from '@/types'

interface StatusUpdate {
  stage: string
  message: string
}

interface UseWebSocketOptions {
  url: string
  onToken?: (token: string) => void
  onVisualization?: (viz: Visualization) => void
  onMetadata?: (meta: MessageMetadata) => void
  onSessionId?: (sessionId: string) => void
  onStatus?: (status: StatusUpdate) => void
  onDone?: () => void
  onError?: (error: string) => void
}

interface UseWebSocketReturn {
  sendMessage: (content: string, sessionId: string) => void
  isConnected: boolean
  isStreaming: boolean
  disconnect: () => void
}

export function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn {
  const {
    url,
    onToken,
    onVisualization,
    onMetadata,
    onSessionId,
    onStatus,
    onDone,
    onError,
  } = options

  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
    setIsStreaming(false)
  }, [])

  const sendMessage = useCallback(
    (content: string, sessionId: string) => {
      // Close existing connection if any
      if (wsRef.current) {
        wsRef.current.close()
      }

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        setIsStreaming(true)

        const message: WSOutgoingMessage = {
          type: 'message',
          content,
          session_id: sessionId,
        }
        ws.send(JSON.stringify(message))
      }

      ws.onmessage = (event) => {
        try {
          const data: WSIncomingMessage = JSON.parse(event.data)

          switch (data.type) {
            case 'session':
              if (data.session_id && onSessionId) {
                onSessionId(data.session_id)
              }
              break

            case 'metadata':
              if (onMetadata) {
                onMetadata({
                  queryType: data.query_type,
                  responseType: data.response_type,
                  confidence: data.confidence,
                })
              }
              break

            case 'token':
              if (data.token && onToken) {
                onToken(data.token)
              }
              break

            case 'visualization':
              if (data.spec && onVisualization) {
                onVisualization(data.spec)
              }
              break

            case 'status':
              if (data.stage && data.message && onStatus) {
                onStatus({ stage: data.stage, message: data.message })
              }
              break

            case 'error':
              if (data.error && onError) {
                onError(data.error)
              }
              break

            case 'done':
              setIsStreaming(false)
              if (onDone) {
                onDone()
              }
              // Close connection after done
              ws.close()
              break
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      ws.onerror = (event) => {
        console.error('WebSocket error:', event)
        if (onError) {
          onError('Connection error. Please try again.')
        }
        setIsStreaming(false)
      }

      ws.onclose = () => {
        setIsConnected(false)
        setIsStreaming(false)
        wsRef.current = null
      }
    },
    [url, onToken, onVisualization, onMetadata, onSessionId, onStatus, onDone, onError]
  )

  return {
    sendMessage,
    isConnected,
    isStreaming,
    disconnect,
  }
}
