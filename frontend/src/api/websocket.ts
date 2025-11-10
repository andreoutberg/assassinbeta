// WebSocket client for real-time updates

import { WebSocketMessage } from '@/types'

const WS_URL = import.meta.env.VITE_PUBLIC_WS_URL || 'ws://localhost:8000/ws'

export type WebSocketCallback = (message: WebSocketMessage) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private reconnectInterval = 5000
  private reconnectTimer: NodeJS.Timeout | null = null
  private callbacks: Set<WebSocketCallback> = new Set()
  private url: string

  constructor(url: string = WS_URL) {
    this.url = url
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        console.log('WebSocket connected')
        this.clearReconnectTimer()
      }

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          this.notifyCallbacks(message)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      this.ws.onclose = () => {
        console.log('WebSocket disconnected, attempting to reconnect...')
        this.scheduleReconnect()
      }
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
      this.scheduleReconnect()
    }
  }

  disconnect() {
    this.clearReconnectTimer()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  subscribe(callback: WebSocketCallback) {
    this.callbacks.add(callback)
    return () => this.unsubscribe(callback)
  }

  unsubscribe(callback: WebSocketCallback) {
    this.callbacks.delete(callback)
  }

  private notifyCallbacks(message: WebSocketMessage) {
    this.callbacks.forEach((callback) => {
      try {
        callback(message)
      } catch (error) {
        console.error('WebSocket callback error:', error)
      }
    })
  }

  private scheduleReconnect() {
    this.clearReconnectTimer()
    this.reconnectTimer = setTimeout(() => {
      this.connect()
    }, this.reconnectInterval)
  }

  private clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

// Global instance
export const wsClient = new WebSocketClient()
