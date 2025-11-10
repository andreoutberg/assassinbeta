// Custom hook for WebSocket connection

import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsClient, WebSocketCallback } from '@/api/websocket'
import { useDashboardStore } from '@/stores/dashboardStore'

export function useWebSocket() {
  const queryClient = useQueryClient()
  const setWsConnected = useDashboardStore((state) => state.setWsConnected)

  useEffect(() => {
    // Connect on mount
    wsClient.connect()
    setWsConnected(wsClient.isConnected)

    // Set up message handler
    const handleMessage: WebSocketCallback = (message) => {
      console.log('WebSocket message received:', message)

      // Invalidate relevant queries based on message type
      switch (message.type) {
        case 'signal':
          queryClient.invalidateQueries({ queryKey: ['signals'] })
          if (message.data?.id) {
            queryClient.invalidateQueries({ queryKey: ['signal', message.data.id] })
          }
          break

        case 'strategy':
          queryClient.invalidateQueries({ queryKey: ['strategies'] })
          if (message.data?.id) {
            queryClient.invalidateQueries({ queryKey: ['strategy', message.data.id] })
            queryClient.invalidateQueries({ queryKey: ['strategy-performance', message.data.id] })
          }
          break

        case 'optimization':
          queryClient.invalidateQueries({ queryKey: ['strategies'] })
          queryClient.invalidateQueries({ queryKey: ['stats'] })
          break

        case 'alert':
          // Could show toast notification here
          console.log('Alert received:', message.data)
          break
      }

      // Always refresh stats
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['stats-by-source'] })
    }

    // Subscribe to messages
    const unsubscribe = wsClient.subscribe(handleMessage)

    // Monitor connection status
    const checkConnectionInterval = setInterval(() => {
      setWsConnected(wsClient.isConnected)
    }, 5000)

    // Cleanup on unmount
    return () => {
      unsubscribe()
      clearInterval(checkConnectionInterval)
      wsClient.disconnect()
    }
  }, [queryClient, setWsConnected])

  return {
    isConnected: useDashboardStore((state) => state.wsConnected),
  }
}
