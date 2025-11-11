import React, { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Brain, TrendingUp, Shield, Zap, BarChart3, Target } from 'lucide-react';
import StrategyCard from '../components/StrategyCard';
import { CollapsibleSection } from '../components/CollapsibleSection';
import clsx from 'clsx';

interface Strategy {
  id: string;
  webhook_source: string;
  phase: 'I' | 'II' | 'III';
  win_rate: number;
  risk_reward: number;
  expected_value: number;
  total_trades: number;
  profitable_trades: number;
  tp_percentage?: number;
  sl_percentage?: number;
  confidence: number;
  optimization_url?: string;
  last_updated: Date | string;
  status: 'active' | 'optimizing' | 'paused';
  performance_trend?: number[];
  avg_trade_duration?: string;
  type?: 'momentum' | 'meanReversion' | 'trend' | 'breakout' | 'scalping';
}

const Strategies: React.FC = () => {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  // Fetch real strategies from API
  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const baseUrl = `${window.location.protocol}//${window.location.hostname}`;
        const response = await fetch(`${baseUrl}/api/strategies`, {
          headers: {
            'Accept': 'application/json',
          },
        });

        if (response.ok) {
          const data = await response.json();
          console.log('Strategies data:', data);
          setStrategies(Array.isArray(data) ? data : []);
        } else {
          console.error('Failed to fetch strategies:', response.status);
          setStrategies([]);
        }
      } catch (error) {
        console.error('Failed to fetch strategies:', error);
        setStrategies([]);
      } finally {
        setLoading(false);
      }
    };

    fetchStrategies();
  }, []);

  const filteredStrategies = useMemo(() => {
    let filtered = [...strategies];

    if (activeFilter !== 'all') {
      filtered = filtered.filter(s =>
        activeFilter === 'active' ? s.status === 'active' : s.status !== 'active'
      );
    }

    if (typeFilter !== 'all') {
      filtered = filtered.filter(s => s.type === typeFilter);
    }

    return filtered;
  }, [strategies, activeFilter, typeFilter]);

  const getOverallStats = () => {
    const activeStrategies = strategies.filter(s => s.status === 'active');
    const totalTrades = strategies.reduce((acc, s) => acc + s.total_trades, 0);
    const avgWinRate = strategies.reduce((acc, s) => acc + s.win_rate, 0) / strategies.length;
    const avgRR = strategies.reduce((acc, s) => acc + s.risk_reward, 0) / strategies.length;

    return {
      total: strategies.length,
      active: activeStrategies.length,
      totalTrades,
      avgWinRate: avgWinRate.toFixed(1),
      avgRR: avgRR.toFixed(2),
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
          <p className="text-caption text-gray-500 dark:text-gray-400">Avg R/R</p>
          <p className="text-title2 font-bold mt-1">{stats.avgRR}</p>
        </div>
      </div>

      {/* Filters */}
      <CollapsibleSection
        title="Filters & Sorting"
        icon={BarChart3}
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
                      ? 'bg-gold text-black font-semibold'
                      : 'glass text-white hover:bg-gray-800/30'
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
                        ? 'bg-gold text-black font-semibold'
                        : 'glass text-white hover:bg-gray-800/30'
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