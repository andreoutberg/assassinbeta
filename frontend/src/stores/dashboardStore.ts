// Zustand store for dashboard state management

import { create } from 'zustand'
import { DashboardFilters, PhaseFilter, DirectionFilter, TimeRange } from '@/types'

interface DashboardState {
  // Filters
  filters: DashboardFilters
  setWebhookSource: (source: string | null) => void
  setPhase: (phase: PhaseFilter) => void
  setDirection: (direction: DirectionFilter) => void
  setSymbol: (symbol: string | null) => void
  setTimeRange: (range: TimeRange) => void
  resetFilters: () => void

  // UI State
  sidebarOpen: boolean
  toggleSidebar: () => void
  selectedSignalId: number | null
  setSelectedSignalId: (id: number | null) => void
  selectedStrategyId: number | null
  setSelectedStrategyId: (id: number | null) => void

  // WebSocket connection status
  wsConnected: boolean
  setWsConnected: (connected: boolean) => void
}

const defaultFilters: DashboardFilters = {
  webhook_source: null,
  phase: 'all',
  direction: 'all',
  symbol: null,
  timeRange: '7d',
}

export const useDashboardStore = create<DashboardState>((set) => ({
  // Initial state
  filters: defaultFilters,
  sidebarOpen: true,
  selectedSignalId: null,
  selectedStrategyId: null,
  wsConnected: false,

  // Filter actions
  setWebhookSource: (source) =>
    set((state) => ({
      filters: { ...state.filters, webhook_source: source },
    })),

  setPhase: (phase) =>
    set((state) => ({
      filters: { ...state.filters, phase },
    })),

  setDirection: (direction) =>
    set((state) => ({
      filters: { ...state.filters, direction },
    })),

  setSymbol: (symbol) =>
    set((state) => ({
      filters: { ...state.filters, symbol },
    })),

  setTimeRange: (range) =>
    set((state) => ({
      filters: { ...state.filters, timeRange: range },
    })),

  resetFilters: () =>
    set({
      filters: defaultFilters,
    }),

  // UI actions
  toggleSidebar: () =>
    set((state) => ({
      sidebarOpen: !state.sidebarOpen,
    })),

  setSelectedSignalId: (id) =>
    set({
      selectedSignalId: id,
    }),

  setSelectedStrategyId: (id) =>
    set({
      selectedStrategyId: id,
    }),

  setWsConnected: (connected) =>
    set({
      wsConnected: connected,
    }),
}))
