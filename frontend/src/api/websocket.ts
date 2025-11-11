// WebSocket client for real-time updates

import { WebSocketMessage } from '@/types'

// Auto-detect WebSocket URL based on current location
const getWebSocketUrl = () => {
  if (import.meta.env.VITE_PUBLIC_WS_URL) {
    return import.meta.env.VITE_PUBLIC_WS_URL
  }

  // Use current hostname with proper port detection
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  // In production, use port 80 (nginx). In dev on :3000, also use :80
  const port = window.location.hostname === 'localhost' && window.location.port === '' ? ':8000' : ':80'
  return `${protocol}//${host}${port}/ws`
}

const WS_URL = getWebSocketUrl()

export type WebSocketCallback = (message: WebSocketMessage) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private reconnectInterval = 1000 // Start with 1 second
  private maxReconnectInterval = 30000 // Max 30 seconds
  private reconnectAttempts = 0
  private reconnectTimer: NodeJS.Timeout | null = null
  private callbacks: Set<WebSocketCallback> = new Set()
  private url: string
  private heartbeatTimer: NodeJS.Timeout | null = null
  private lastHeartbeatTime: number = 0
  private readonly heartbeatTimeoutThreshold = 45000 // 45 seconds without heartbeat = disconnect

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
        if (import.meta.env.DEV) {
          console.log('WebSocket connected')
        }
        this.clearReconnectTimer()
        this.reconnectAttempts = 0
        this.reconnectInterval = 1000 // Reset to 1 second on successful connection
        this.startHeartbeat()
      }

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)

          // Handle heartbeat messages
          if (message.type === 'heartbeat') {
            this.lastHeartbeatTime = Date.now()
            // Send pong response
            this.send({ type: 'pong' })
            return
          }

          // Handle acknowledgment requests
          if (message.require_ack && message.message_id) {
            this.send({ type: 'ack', message_id: message.message_id })
          }

          this.notifyCallbacks(message)
        } catch (error) {
          if (import.meta.env.DEV) {
            console.error('Failed to parse WebSocket message:', error)
          }
        }
      }

      this.ws.onerror = (error) => {
        if (import.meta.env.DEV) {
          console.error('WebSocket error:', error)
        }
      }

      this.ws.onclose = () => {
        if (import.meta.env.DEV) {
          console.log('WebSocket disconnected, attempting to reconnect...')
        }
        this.stopHeartbeat()
        this.scheduleReconnect()
      }
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error('Failed to create WebSocket connection:', error)
      }
      this.scheduleReconnect()
    }
  }

  disconnect() {
    this.clearReconnectTimer()
    this.stopHeartbeat()
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

  subscribeToChannel(channelType: 'symbol' | 'phase', channelValue: string) {
    this.send({
      type: 'subscribe',
      channel_type: channelType,
      channel_value: channelValue,
    })
  }

  unsubscribeFromChannel(channelType: 'symbol' | 'phase', channelValue: string) {
    this.send({
      type: 'unsubscribe',
      channel_type: channelType,
      channel_value: channelValue,
    })
  }

  private send(data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  private notifyCallbacks(message: WebSocketMessage) {
    this.callbacks.forEach((callback) => {
      try {
        callback(message)
      } catch (error) {
        if (import.meta.env.DEV) {
          console.error('WebSocket callback error:', error)
        }
      }
    })
  }

  private scheduleReconnect() {
    this.clearReconnectTimer()

    // Exponential backoff with jitter
    const jitter = Math.random() * 1000 // Add up to 1 second of jitter
    const backoffDelay = Math.min(
      this.reconnectInterval * Math.pow(2, this.reconnectAttempts),
      this.maxReconnectInterval
    ) + jitter

    if (import.meta.env.DEV) {
      console.log(
        `Scheduling reconnect attempt ${this.reconnectAttempts + 1} in ${Math.round(backoffDelay)}ms`
      )
    }

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++
      this.connect()
    }, backoffDelay)
  }

  private clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private startHeartbeat() {
    this.stopHeartbeat()
    this.lastHeartbeatTime = Date.now()

    // Check for missed heartbeats every 15 seconds
    this.heartbeatTimer = setInterval(() => {
      const timeSinceLastHeartbeat = Date.now() - this.lastHeartbeatTime

      if (timeSinceLastHeartbeat > this.heartbeatTimeoutThreshold) {
        if (import.meta.env.DEV) {
          console.warn('Heartbeat timeout detected, reconnecting...')
        }
        this.disconnect()
        this.connect()
      }
    }, 15000)
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

// Global instance
export const wsClient = new WebSocketClient()
