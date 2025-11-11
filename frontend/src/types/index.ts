// Core data types matching backend API

export interface Signal {
  id: number
  symbol: string
  direction: 'LONG' | 'SHORT'
  entry_price: number
  timeframe: string
  webhook_source: string
  phase: 'I' | 'II' | 'III'
  status: string
  created_at: string
  updated_at: string
  take_profit_price?: number
  stop_loss_price?: number
  exit_price?: number
  exit_reason?: string
  pnl?: number
  pnl_pct?: number
}

export interface Strategy {
  id: number
  symbol: string
  direction: 'LONG' | 'SHORT'
  webhook_source: string
  phase: 'I' | 'II' | 'III'
  take_profit_pct: number
  stop_loss_pct: number
  win_rate: number
  rr_ratio: number
  expected_value: number
  trades_analyzed: number
  created_at: string
  is_active: boolean
  optimization_method: 'grid_search' | 'optuna' | 'manual'
  confidence_score?: number
}

export interface StrategyPerformance {
  strategy_id: number
  win_rate: number
  total_trades: number
  wins: number
  losses: number
  avg_profit: number
  avg_loss: number
  profit_factor: number
  sharpe_ratio?: number
  max_drawdown?: number
}

export interface Stats {
  total_signals: number
  total_strategies: number
  active_strategies: number
  overall_win_rate: number
  total_pnl: number
  total_pnl_pct: number
  best_strategy?: Strategy
  worst_strategy?: Strategy
}

export interface StatsBySource {
  webhook_source: string
  signal_count: number
  strategy_count: number
  win_rate: number
  total_pnl: number
  phase_distribution: {
    phase_i: number
    phase_ii: number
    phase_iii: number
  }
}

export interface WebSocketMessage {
  type: 'signal' | 'strategy' | 'optimization' | 'alert' | 'heartbeat' | 'pong' | 'connection' | 'subscribed' | 'unsubscribed' | 'stats'
  action?: 'created' | 'updated' | 'deleted'
  data: any
  message_id?: string
  require_ack?: boolean
}

export interface OptunaTrial {
  trial_id: number
  params: {
    take_profit_pct: number
    stop_loss_pct: number
    [key: string]: any
  }
  values: number[]  // [win_rate, rr_ratio, expected_value]
  state: 'COMPLETE' | 'RUNNING' | 'PRUNED' | 'FAIL'
  datetime_start: string
  datetime_complete?: string
}

export interface OptunaStudy {
  study_name: string
  direction: string[]
  n_trials: number
  best_trials: OptunaTrial[]
  datetime_start: string
}

// Dashboard state types
export type PhaseFilter = 'all' | 'I' | 'II' | 'III'
export type DirectionFilter = 'all' | 'LONG' | 'SHORT'
export type TimeRange = '1h' | '24h' | '7d' | '30d' | 'all'

export interface DashboardFilters {
  webhook_source: string | null
  phase: PhaseFilter
  direction: DirectionFilter
  symbol: string | null
  timeRange: TimeRange
}
