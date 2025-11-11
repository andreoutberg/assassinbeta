// Custom hook for strategies data with TanStack Query

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/api/client'

export function useStrategies(params?: {
  webhook_source?: string
  phase?: string
  is_active?: boolean
}) {
  return useQuery({
    queryKey: ['strategies', params],
    queryFn: () => apiClient.getStrategies(params),
    refetchInterval: false, // Use WebSocket for real-time updates
    staleTime: 15000,
  })
}

export function useStrategy(id: number | null) {
  return useQuery({
    queryKey: ['strategy', id],
    queryFn: () => (id ? apiClient.getStrategy(id) : null),
    enabled: !!id,
  })
}

export function useStrategyPerformance(id: number | null) {
  return useQuery({
    queryKey: ['strategy-performance', id],
    queryFn: () => (id ? apiClient.getStrategyPerformance(id) : null),
    enabled: !!id,
    refetchInterval: 60000,
  })
}
