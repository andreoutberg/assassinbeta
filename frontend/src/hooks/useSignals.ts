// Custom hook for signals data with TanStack Query

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/api/client'

export function useSignals(params?: { webhook_source?: string; phase?: string; limit?: number }) {
  return useQuery({
    queryKey: ['signals', params],
    queryFn: () => apiClient.getSignals(params),
    refetchInterval: false, // Use WebSocket for real-time updates
    staleTime: 15000, // Consider data stale after 15 seconds
  })
}

export function useSignal(id: number | null) {
  return useQuery({
    queryKey: ['signal', id],
    queryFn: () => (id ? apiClient.getSignal(id) : null),
    enabled: !!id,
  })
}
