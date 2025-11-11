// Custom hook for stats data

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/api/client'

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => apiClient.getStats(),
    refetchInterval: 30000,
    staleTime: 60000, // Increased from 15000 to 60000
  })
}

export function useStatsBySource() {
  return useQuery({
    queryKey: ['stats-by-source'],
    queryFn: () => apiClient.getStatsBySource(),
    refetchInterval: 30000,
    staleTime: 15000,
  })
}

export function useWebhookSources() {
  return useQuery({
    queryKey: ['webhook-sources'],
    queryFn: () => apiClient.getWebhookSources(),
    staleTime: 300000, // 5 minutes
  })
}
