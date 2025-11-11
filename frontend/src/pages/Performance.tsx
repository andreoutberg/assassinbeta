import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, DollarSign, Activity, Target,  Award } from 'lucide-react';
import { WinRateGauge } from '../components/Charts/WinRateGauge';
import { CollapsibleSection } from '../components/CollapsibleSection';
import StatCard from '../components/StatCard';
import clsx from 'clsx';

type TabType = 'overview' | 'bySource' | 'pareto';

const Performance: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [timeRange, setTimeRange] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [overallStats, setOverallStats] = useState<any>({
    totalProfit: 0,
    totalReturn: 0,
    winRate: 0,
    sharpeRatio: 0,
    maxDrawdown: 0,
    profitFactor: 0,
    totalTrades: 0,
    avgTradeProfit: 0,
  });

  useEffect(() => {
    const fetchPerformanceData = async () => {
      try {
        const baseUrl = `${window.location.protocol}//${window.location.hostname}`;
        const [statsRes, tradesRes] = await Promise.all([
          fetch(`${baseUrl}/api/overview/stats`),
          fetch(`${baseUrl}/api/trades/active`)
        ]);

        if (statsRes.ok && tradesRes.ok) {
          const stats = await statsRes.json();
          const trades = await tradesRes.json();

          // Calculate basic stats from real data
          setOverallStats({
            totalProfit: 0,
            totalReturn: 0,
            winRate: stats.overall_win_rate || 0,
            sharpeRatio: 0,
            maxDrawdown: 0,
            profitFactor: 0,
            totalTrades: trades.count || 0,
            avgTradeProfit: 0,
          });
        }
      } catch (error) {
        console.error('Failed to fetch performance data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchPerformanceData();
  }, [timeRange]);

  const timeRanges = [
    { value: '7d', label: '7 Days' },
    { value: '30d', label: '30 Days' },
    { value: '90d', label: '3 Months' },
    { value: '180d', label: '6 Months' },
    { value: '1y', label: '1 Year' },
    { value: 'all', label: 'All Time' },
  ];

  const tabs: { value: TabType; label: string; icon: React.ReactNode }[] = [
    { value: 'overview', label: 'Overview', icon: <Activity className="w-4 h-4" /> },
    { value: 'bySource', label: 'By Source', icon: <Target className="w-4 h-4" /> },
    { value: 'pareto', label: 'Pareto Analysis', icon: <Award className="w-4 h-4" /> },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
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
          <h1 className="text-[28px] font-semibold text-white mb-1">Performance Analytics</h1>
          <p className="text-[15px] text-gray-400">Track your trading performance over time</p>
        </div>

        {/* Time Range Selector */}
        <div className="flex gap-2">
          {timeRanges.map(range => (
            <button
              key={range.value}
              onClick={() => setTimeRange(range.value)}
              className={clsx(
                'px-3 py-1.5 rounded-ios text-[13px] font-medium transition-all',
                timeRange === range.value
                  ? 'bg-gold text-black font-semibold'
                  : 'glass text-white hover:bg-gray-800/30'
              )}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-800">
        {tabs.map(tab => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={clsx(
              'flex items-center gap-2 px-4 py-3 text-[15px] font-medium transition-all',
              activeTab === tab.value
                ? 'text-gold border-b-2 border-gold'
                : 'text-gray-400 hover:text-gray-200'
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          value={`$${overallStats.totalProfit.toLocaleString()}`}
          label="Total Profit"
          icon={DollarSign}
          color="success"
        />
        <StatCard
          value={`${overallStats.totalReturn}%`}
          label="Total Return"
          icon={TrendingUp}
          color="gold"
        />
        <StatCard
          value={`${overallStats.winRate.toFixed(1)}%`}
          label="Win Rate"
          icon={Target}
          color="blue"
        />
        <StatCard
          value={overallStats.totalTrades}
          label="Total Trades"
          icon={Activity}
          color="gold"
        />
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <CollapsibleSection title="Performance Metrics" defaultOpen={true}>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div className="card-dark p-4">
                <p className="text-[11px] text-gray-400 mb-1">Sharpe Ratio</p>
                <p className="text-[20px] font-bold text-white">{overallStats.sharpeRatio.toFixed(2)}</p>
              </div>
              <div className="card-dark p-4">
                <p className="text-[11px] text-gray-400 mb-1">Max Drawdown</p>
                <p className="text-[20px] font-bold text-ios-red">{overallStats.maxDrawdown}%</p>
              </div>
              <div className="card-dark p-4">
                <p className="text-[11px] text-gray-400 mb-1">Profit Factor</p>
                <p className="text-[20px] font-bold text-gold">{overallStats.profitFactor.toFixed(2)}</p>
              </div>
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="Win Rate Distribution" defaultOpen={true}>
            <div className="card-dark p-6 flex items-center justify-center">
              <WinRateGauge value={overallStats.winRate} size="lg" />
            </div>
          </CollapsibleSection>
        </div>
      )}

      {activeTab === 'bySource' && (
        <div className="space-y-4">
          <p className="text-gray-400 text-center py-8">No source performance data available yet</p>
        </div>
      )}

      {activeTab === 'pareto' && (
        <div className="space-y-4">
          <p className="text-gray-400 text-center py-8">No Pareto analysis data available yet</p>
        </div>
      )}
    </motion.div>
  );
};

export default Performance;
