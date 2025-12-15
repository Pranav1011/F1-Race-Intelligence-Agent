// API configuration
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const API_ENDPOINTS = {
  chat: `${API_BASE_URL}/api/v1/chat/`,
  chatWs: `${API_BASE_URL.replace('http', 'ws')}/api/v1/chat/ws`,
  health: `${API_BASE_URL}/api/v1/health`,
}

// HTTP chat API (fallback if WebSocket fails)
export async function sendChatMessage(content: string, sessionId?: string) {
  const response = await fetch(API_ENDPOINTS.chat, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      session_id: sessionId,
    }),
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  return response.json()
}
