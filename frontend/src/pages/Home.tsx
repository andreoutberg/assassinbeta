import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, Layers, BarChart3, DollarSign, Activity, Target, Zap, Clock } from 'lucide-react';
import { StatCard } from '../components/StatCard';
import { CollapsibleSection } from '../components/CollapsibleSection';
import { SignalCard } from '../components/SignalCard';
import { StrategyCard } from '../components/StrategyCard';
import { WinRateGauge } from '../components/Charts/WinRateGauge';
import { LoadingSpinner } from '../components/LoadingSpinner';
import clsx from 'clsx';

// Mock data - replace with actual API calls
const mockStats = {
  totalSignals: 342,
  activeStrategies: 8,
  overallWinRate: 68.5,
  totalPnL: 12450.75,
  todayPnL: 345.20,
  weekPnL: 2150.60,
};

const mockRecentSignals = [
  {
    id: '1',
    symbol: 'BTC/USDT',
    direction: 'LONG' as const,
    entry_price: 43250.50,
    current_price: 43850.75,
    tp_price: 44500,
    sl_price: 42500,
    pnl: 600.25,
    pnl_percentage: 1.39,
    phase: 'III' as const,
    webhook_source: 'TradingView_Premium',
    timestamp: new Date(Date.now() - 3600000),
    status: 'active' as const,
    confidence: 78,
    risk_reward: 2.5,
  },
  // Add more mock signals...
];

const mockActiveStrategies = [
  {
    id: '1',
    webhook_source: 'TradingView_Premium',
    phase: 'III' as const,
    win_rate: 72.5,
    risk_reward: 2.3,
    expected_value: 8.5,
    total_trades: 156,
    profitable_trades: 113,
    tp_percentage: 3.5,
    sl_percentage: 1.5,
    confidence: 85,
    optimization_url: 'https://optuna.example.com/study/1',
    last_updated: new Date(),
    status: 'active' as const,
    performance_trend: [65, 70, 68, 75, 72, 78, 73],
    avg_trade_duration: '4h 32m',
  },
  // Add more mock strategies...
];

const mockOptimizationQueue = [
  {
    id: '2',
    webhook_source: 'Custom_Signal_A',
    phase: 'II' as const,
    win_rate: 58.2,
    risk_reward: 1.8,
    expected_value: 2.3,
    total_trades: 45,
    profitable_trades: 26,
    confidence: 62,
    optimization_url: 'https://optuna.example.com/study/2',
    last_updated: new Date(),
    status: 'optimizing' as const,
  },
];

export const Home: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(mockStats);

  useEffect(() => {
    // Simulate loading
    setTimeout(() => setLoading(false), 1000);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner size="lg" text="Loading dashboard..." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <h1 className="text-largeTitle font-bold text-gray-900 dark:text-gray-50 mb-2">
          Dashboard Overview
        </h1>
        <p className="text-body text-gray-600 dark:text-gray-400">
          Real-time trading performance and strategy insights
        </p>
      </motion.div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          value={stats.totalSignals}
          label="Total Signals"
          icon={TrendingUp}
          color="blue"
          trend="up"
          trendValue="+12%"
        />
        <StatCard
          value={stats.activeStrategies}
          label="Active Strategies"
          icon={Layers}
          color="gold"
        />
        <StatCard
          value={`${stats.overallWinRate.toFixed(1)}%`}
          label="Win Rate"
          icon={Target}
          color="success"
          trend="up"
          trendValue="+3.2%"
        />
        <StatCard
          value={`$${stats.totalPnL.toLocaleString()}`}
          label="Total P&L"
          icon={DollarSign}
          color={stats.totalPnL >= 0 ? 'success' : 'danger'}
          trend={stats.totalPnL >= 0 ? 'up' : 'down'}
          trendValue={`${stats.totalPnL >= 0 ? '+' : ''}${((stats.totalPnL / 10000) * 100).toFixed(1)}%`}
        />
      </div>

      {/* Quick Stats Section */}
      <CollapsibleSection
        title="Quick Stats"
        summary={`Today: ${stats.todayPnL >= 0 ? '+' : ''}$${stats.todayPnL.toFixed(2)} | Week: ${stats.weekPnL >= 0 ? '+' : ''}$${stats.weekPnL.toFixed(2)}`}
        defaultOpen={true}
        icon={BarChart3}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Win Rate Gauge */}
          <div className="card-ios p-6 flex items-center justify-center">
            <WinRateGauge
              value={stats.overallWinRate}
              size="md"
            />
          </div>

          {/* Performance Summary */}
          <div className="space-y-4">
            <div className="glass rounded-ios p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-body text-gray-600 dark:text-gray-300">
                  Today's Performance
                </span>
                <span className={clsx(
                  'text-headline font-semibold',
                  stats.todayPnL >= 0 ? 'text-success' : 'text-danger'
                )}>
                  {stats.todayPnL >= 0 ? '+' : ''}${stats.todayPnL.toFixed(2)}
                </span>
              </div>
              <div className="h-1 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.abs(stats.todayPnL) / 10}%` }}
                  className={clsx(
                    'h-full',
                    stats.todayPnL >= 0 ? 'bg-success' : 'bg-danger'
                  )}
                />
              </div>
            </div>

            <div className="glass rounded-ios p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-body text-gray-600 dark:text-gray-300">
                  Weekly Performance
                </span>
                <span className={clsx(
                  'text-headline font-semibold',
                  stats.weekPnL >= 0 ? 'text-success' : 'text-danger'
                )}>
                  {stats.weekPnL >= 0 ? '+' : ''}${stats.weekPnL.toFixed(2)}
                </span>
              </div>
              <div className="h-1 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.abs(stats.weekPnL) / 30}%` }}
                  className={clsx(
                    'h-full',
                    stats.weekPnL >= 0 ? 'bg-success' : 'bg-danger'
                  )}
                />
              </div>
            </div>

            <div className="glass rounded-ios p-4">
              <div className="flex items-center gap-3">
                <Activity className="w-5 h-5 text-gold" />
                <div className="flex-1">
                  <p className="text-caption text-gray-600 dark:text-gray-300">
                    Market Activity
                  </p>
                  <p className="text-body font-semibold text-gray-900 dark:text-gray-50">
                    High Volume
                  </p>
                </div>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <motion.div
                      key={i}
                      initial={{ height: 0 }}
                      animate={{ height: `${20 + Math.random() * 30}px` }}
                      transition={{ duration: 0.5, delay: i * 0.1 }}
                      className="w-1 bg-gold rounded-full"
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </CollapsibleSection>

      {/* Recent Signals */}
      <CollapsibleSection
        title="Recent Signals"
        summary={`${mockRecentSignals.length} active signals`}
        defaultOpen={true}
        icon={TrendingUp}
        badge={
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 bg-ios-green rounded-full animate-pulse" />
            <span className="text-caption text-ios-green">Live</span>
          </div>
        }
      >
        <div className="space-y-3">
          {mockRecentSignals.slice(0, 5).map((signal) => (
            <SignalCard key={signal.id} signal={signal} />
          ))}
        </div>
      </CollapsibleSection>

      {/* Active Strategies */}
      <CollapsibleSection
        title="Active Strategies"
        summary={`${mockActiveStrategies.length} strategies, ${stats.overallWinRate.toFixed(1)}% avg WR`}
        defaultOpen={false}
        icon={Layers}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {mockActiveStrategies.map((strategy) => (
            <StrategyCard key={strategy.id} strategy={strategy} />
          ))}
        </div>
      </CollapsibleSection>

      {/* Optimization Queue */}
      <CollapsibleSection
        title="Optimization Queue"
        summary={`${mockOptimizationQueue.length} strategies optimizing`}
        defaultOpen={false}
        icon={Zap}
        badge={
          mockOptimizationQueue.length > 0 ? (
            <span className="badge-phase-ii">Phase II</span>
          ) : null
        }
      >
        <div className="space-y-4">
          {mockOptimizationQueue.map((strategy) => (
            <StrategyCard key={strategy.id} strategy={strategy} />
          ))}

          {/* Progress indicator */}
          <div className="glass rounded-ios p-4">
            <div className="flex items-center gap-3 mb-3">
              <Clock className="w-4 h-4 text-gold animate-spin-slow" />
              <span className="text-body text-gray-600 dark:text-gray-300">
                Optimization Progress
              </span>
            </div>
            <div className="h-2 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: '65%' }}
                transition={{ duration: 2, ease: 'easeInOut' }}
                className="h-full bg-gradient-to-r from-gold to-gold-light"
              />
            </div>
            <p className="text-caption text-gray-500 dark:text-gray-400 mt-2">
              Estimated time remaining: 2h 15m
            </p>
          </div>
        </div>
      </CollapsibleSection>
    </div>
  );
};