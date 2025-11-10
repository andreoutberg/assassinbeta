import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Brain, TrendingUp, Shield, Zap, BarChart3, Target } from 'lucide-react';
import StrategyCard from '../components/StrategyCard';
import CollapsibleSection from '../components/CollapsibleSection';
import clsx from 'clsx';

interface Strategy {
  id: string;
  name: string;
  description: string;
  type: 'momentum' | 'meanReversion' | 'trend' | 'breakout' | 'scalping';
  isActive: boolean;
  performance: {
    winRate: number;
    profitFactor: number;
    sharpeRatio: number;
    totalTrades: number;
    profitableTrades: number;
    averageWin: number;
    averageLoss: number;
    maxDrawdown: number;
  };
  parameters?: {
    timeframe: string;
    riskPercent: number;
    stopLoss: number;
    takeProfit: number;
  };
  lastSignal?: {
    timestamp: Date;
    type: 'BUY' | 'SELL';
    symbol: string;
    price: number;
  };
}

const Strategies: React.FC = () => {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  // Mock data
  useEffect(() => {
    const mockStrategies: Strategy[] = [
      {
        id: '1',
        name: 'Ichimoku Cloud Master',
        description: 'Advanced Ichimoku cloud strategy with multi-timeframe analysis',
        type: 'trend',
        isActive: true,
        performance: {
          winRate: 0.68,
          profitFactor: 2.4,
          sharpeRatio: 1.8,
          totalTrades: 156,
          profitableTrades: 106,
          averageWin: 850,
          averageLoss: 320,
          maxDrawdown: 0.12,
        },
        parameters: {
          timeframe: '4H',
          riskPercent: 2,
          stopLoss: 3,
          takeProfit: 6,
        },
        lastSignal: {
          timestamp: new Date(),
          type: 'BUY',
          symbol: 'BTC/USD',
          price: 95000,
        },
      },
      {
        id: '2',
        name: 'Wyckoff Accumulation',
        description: 'Identifies accumulation phases using Wyckoff methodology',
        type: 'breakout',
        isActive: true,
        performance: {
          winRate: 0.72,
          profitFactor: 2.8,
          sharpeRatio: 2.1,
          totalTrades: 89,
          profitableTrades: 64,
          averageWin: 1200,
          averageLoss: 400,
          maxDrawdown: 0.09,
        },
        parameters: {
          timeframe: '1D',
          riskPercent: 1.5,
          stopLoss: 4,
          takeProfit: 8,
        },
        lastSignal: {
          timestamp: new Date(Date.now() - 3600000),
          type: 'SELL',
          symbol: 'ETH/USD',
          price: 3200,
        },
      },
      {
        id: '3',
        name: 'Smart Money Flow',
        description: 'Tracks institutional money flow patterns',
        type: 'momentum',
        isActive: false,
        performance: {
          winRate: 0.65,
          profitFactor: 2.1,
          sharpeRatio: 1.6,
          totalTrades: 234,
          profitableTrades: 152,
          averageWin: 650,
          averageLoss: 280,
          maxDrawdown: 0.15,
        },
        parameters: {
          timeframe: '1H',
          riskPercent: 2.5,
          stopLoss: 2,
          takeProfit: 4,
        },
      },
      {
        id: '4',
        name: 'Scalping Pro',
        description: 'High-frequency scalping with tight risk management',
        type: 'scalping',
        isActive: true,
        performance: {
          winRate: 0.58,
          profitFactor: 1.6,
          sharpeRatio: 1.2,
          totalTrades: 512,
          profitableTrades: 297,
          averageWin: 120,
          averageLoss: 80,
          maxDrawdown: 0.08,
        },
        parameters: {
          timeframe: '5M',
          riskPercent: 1,
          stopLoss: 0.5,
          takeProfit: 1,
        },
      },
    ];
    setStrategies(mockStrategies);
    setLoading(false);
  }, []);

  const getFilteredStrategies = () => {
    let filtered = [...strategies];

    if (activeFilter !== 'all') {
      filtered = filtered.filter(s =>
        activeFilter === 'active' ? s.isActive : !s.isActive
      );
    }

    if (typeFilter !== 'all') {
      filtered = filtered.filter(s => s.type === typeFilter);
    }

    return filtered;
  };

  const filteredStrategies = getFilteredStrategies();

  const getOverallStats = () => {
    const activeStrategies = strategies.filter(s => s.isActive);
    const totalTrades = strategies.reduce((acc, s) => acc + s.performance.totalTrades, 0);
    const avgWinRate = strategies.reduce((acc, s) => acc + s.performance.winRate, 0) / strategies.length;
    const avgSharpe = strategies.reduce((acc, s) => acc + s.performance.sharpeRatio, 0) / strategies.length;

    return {
      total: strategies.length,
      active: activeStrategies.length,
      totalTrades,
      avgWinRate: (avgWinRate * 100).toFixed(1),
      avgSharpe: avgSharpe.toFixed(2),
    };
  };

  const stats = getOverallStats();

  const strategyTypes = [
    { value: 'all', label: 'All Types', icon: Brain },
    { value: 'trend', label: 'Trend Following', icon: TrendingUp },
    { value: 'momentum', label: 'Momentum', icon: Zap },
    { value: 'breakout', label: 'Breakout', icon: Target },
    { value: 'meanReversion', label: 'Mean Reversion', icon: BarChart3 },
    { value: 'scalping', label: 'Scalping', icon: Shield },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold"></div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-largeTitle font-bold gold-gradient-text">Trading Strategies</h1>
          <p className="text-body text-gray-600 dark:text-gray-400 mt-1">
            Manage and monitor your automated trading strategies
          </p>
        </div>
        <button className="ios-button-gold">
          Add Strategy
        </button>
      </div>

      {/* Overall Statistics */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="ios-card p-4">
          <p className="text-caption text-gray-500 dark:text-gray-400">Total Strategies</p>
          <p className="text-title2 font-bold mt-1">{stats.total}</p>
        </div>
        <div className="ios-card p-4">
          <p className="text-caption text-gray-500 dark:text-gray-400">Active</p>
          <p className="text-title2 font-bold text-ios-green mt-1">{stats.active}</p>
        </div>
        <div className="ios-card p-4">
          <p className="text-caption text-gray-500 dark:text-gray-400">Total Trades</p>
          <p className="text-title2 font-bold mt-1">{stats.totalTrades}</p>
        </div>
        <div className="ios-card p-4">
          <p className="text-caption text-gray-500 dark:text-gray-400">Avg Win Rate</p>
          <p className="text-title2 font-bold text-gold mt-1">{stats.avgWinRate}%</p>
        </div>
        <div className="ios-card p-4">
          <p className="text-caption text-gray-500 dark:text-gray-400">Avg Sharpe</p>
          <p className="text-title2 font-bold mt-1">{stats.avgSharpe}</p>
        </div>
      </div>

      {/* Filters */}
      <CollapsibleSection
        title="Filters & Sorting"
        icon={<BarChart3 className="w-5 h-5" />}
        defaultOpen={false}
      >
        <div className="space-y-4">
          {/* Status Filter */}
          <div>
            <label className="text-caption text-gray-600 dark:text-gray-400 mb-2 block">
              Status
            </label>
            <div className="flex gap-2">
              {['all', 'active', 'inactive'].map(status => (
                <button
                  key={status}
                  onClick={() => setActiveFilter(status as any)}
                  className={clsx(
                    'px-4 py-2 rounded-ios text-body capitalize transition-all',
                    activeFilter === status
                      ? 'bg-gold text-gray-900'
                      : 'glass hover:bg-white/90 dark:hover:bg-gray-800/90'
                  )}
                >
                  {status}
                </button>
              ))}
            </div>
          </div>

          {/* Type Filter */}
          <div>
            <label className="text-caption text-gray-600 dark:text-gray-400 mb-2 block">
              Strategy Type
            </label>
            <div className="flex flex-wrap gap-2">
              {strategyTypes.map(type => {
                const Icon = type.icon;
                return (
                  <button
                    key={type.value}
                    onClick={() => setTypeFilter(type.value)}
                    className={clsx(
                      'px-3 py-2 rounded-ios text-body flex items-center gap-2 transition-all',
                      typeFilter === type.value
                        ? 'bg-gold text-gray-900'
                        : 'glass hover:bg-white/90 dark:hover:bg-gray-800/90'
                    )}
                  >
                    <Icon className="w-4 h-4" />
                    {type.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </CollapsibleSection>

      {/* Strategies Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {filteredStrategies.length > 0 ? (
          filteredStrategies.map((strategy, index) => (
            <motion.div
              key={strategy.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: index * 0.1 }}
            >
              <StrategyCard
                strategy={strategy}
                onToggle={() => {
                  const updated = strategies.map(s =>
                    s.id === strategy.id ? { ...s, isActive: !s.isActive } : s
                  );
                  setStrategies(updated);
                }}
                onEdit={() => console.log('Edit strategy', strategy.id)}
                onViewDetails={() => console.log('View details', strategy.id)}
              />
            </motion.div>
          ))
        ) : (
          <div className="col-span-2 ios-card p-12 text-center">
            <Brain className="w-16 h-16 text-gray-400 mx-auto mb-4" />
            <p className="text-title2 text-gray-600 dark:text-gray-400">
              No strategies found
            </p>
            <p className="text-body text-gray-500 dark:text-gray-500 mt-2">
              Try adjusting your filters or add a new strategy
            </p>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default Strategies;