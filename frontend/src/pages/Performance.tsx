import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, Calendar, DollarSign, Activity, Target, Shield, Award } from 'lucide-react';
import PerformanceLineChart from '../components/Charts/PerformanceLineChart';
import ParetoScatterChart from '../components/Charts/ParetoScatterChart';
import WinRateGauge from '../components/Charts/WinRateGauge';
import CollapsibleSection from '../components/CollapsibleSection';
import StatCard from '../components/StatCard';
import clsx from 'clsx';

type TabType = 'overview' | 'bySource' | 'pareto';

const Performance: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [timeRange, setTimeRange] = useState('30d');

  // Mock performance data
  const performanceData = [
    { date: '2024-01-01', value: 10000, benchmark: 10000, volume: 50000 },
    { date: '2024-01-15', value: 10500, benchmark: 10200, volume: 55000 },
    { date: '2024-02-01', value: 11200, benchmark: 10300, volume: 62000 },
    { date: '2024-02-15', value: 11800, benchmark: 10500, volume: 58000 },
    { date: '2024-03-01', value: 12500, benchmark: 10800, volume: 71000 },
    { date: '2024-03-15', value: 13200, benchmark: 11000, volume: 68000 },
    { date: '2024-04-01', value: 14100, benchmark: 11200, volume: 75000 },
  ];

  const sourcePerformance = {
    Ichimoku: {
      winRate: 0.68,
      profitFactor: 2.4,
      totalTrades: 156,
      totalProfit: 12500,
      data: [
        { date: '2024-01', value: 2500 },
        { date: '2024-02', value: 3200 },
        { date: '2024-03', value: 3800 },
        { date: '2024-04', value: 3000 },
      ],
    },
    Wyckoff: {
      winRate: 0.72,
      profitFactor: 2.8,
      totalTrades: 89,
      totalProfit: 9800,
      data: [
        { date: '2024-01', value: 2000 },
        { date: '2024-02', value: 2500 },
        { date: '2024-03', value: 2800 },
        { date: '2024-04', value: 2500 },
      ],
    },
    SmartMoney: {
      winRate: 0.65,
      profitFactor: 2.1,
      totalTrades: 234,
      totalProfit: 8900,
      data: [
        { date: '2024-01', value: 1800 },
        { date: '2024-02', value: 2200 },
        { date: '2024-03', value: 2500 },
        { date: '2024-04', value: 2400 },
      ],
    },
  };

  const paretoData = [
    { strategy: 'Ichimoku', profit: 12500, trades: 156, efficiency: 80.13 },
    { strategy: 'Wyckoff', profit: 9800, trades: 89, efficiency: 110.11 },
    { strategy: 'SmartMoney', profit: 8900, trades: 234, efficiency: 38.03 },
    { strategy: 'Scalping', profit: 5600, trades: 512, efficiency: 10.94 },
    { strategy: 'Breakout', profit: 4200, trades: 67, efficiency: 62.69 },
  ];

  const overallStats = {
    totalProfit: 41000,
    totalReturn: 41,
    winRate: 68.5,
    sharpeRatio: 1.8,
    maxDrawdown: 12,
    profitFactor: 2.4,
    totalTrades: 1058,
    avgTradeProfit: 38.75,
  };

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

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-largeTitle font-bold gold-gradient-text">Performance Analytics</h1>
          <p className="text-body text-gray-600 dark:text-gray-400 mt-1">
            Track your trading performance and profitability
          </p>
        </div>

        {/* Time Range Selector */}
        <div className="flex gap-2">
          {timeRanges.map(range => (
            <button
              key={range.value}
              onClick={() => setTimeRange(range.value)}
              className={clsx(
                'px-3 py-1.5 rounded-ios text-caption transition-all',
                timeRange === range.value
                  ? 'bg-gold text-gray-900'
                  : 'glass hover:bg-white/90 dark:hover:bg-gray-800/90'
              )}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 p-1 glass rounded-ios-lg overflow-x-auto">
        {tabs.map(tab => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-ios whitespace-nowrap transition-all',
              activeTab === tab.value
                ? 'bg-gold text-gray-900 font-medium'
                : 'hover:bg-white/50 dark:hover:bg-gray-800/50'
            )}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {/* Key Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              title="Total Profit"
              value={`$${overallStats.totalProfit.toLocaleString()}`}
              change={`+${overallStats.totalReturn}%`}
              trend="up"
              icon={<DollarSign className="w-5 h-5" />}
            />
            <StatCard
              title="Win Rate"
              value={`${overallStats.winRate}%`}
              change="+3.2%"
              trend="up"
              icon={<TrendingUp className="w-5 h-5" />}
            />
            <StatCard
              title="Sharpe Ratio"
              value={overallStats.sharpeRatio.toFixed(2)}
              change="+0.2"
              trend="up"
              icon={<Shield className="w-5 h-5" />}
            />
            <StatCard
              title="Max Drawdown"
              value={`${overallStats.maxDrawdown}%`}
              change="-2%"
              trend="down"
              icon={<Activity className="w-5 h-5" />}
            />
          </div>

          {/* Performance Chart */}
          <PerformanceLineChart
            data={performanceData}
            title="Portfolio Performance"
            showBenchmark={true}
            showVolume={false}
            type="area"
            height={400}
          />

          {/* Additional Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <WinRateGauge
              winRate={overallStats.winRate}
              totalTrades={overallStats.totalTrades}
              profitableTrades={Math.round(overallStats.totalTrades * overallStats.winRate / 100)}
            />

            <CollapsibleSection
              title="Trading Statistics"
              icon={<Activity className="w-5 h-5" />}
              defaultOpen={true}
            >
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-body text-gray-600 dark:text-gray-400">Profit Factor</span>
                  <span className="text-body font-medium">{overallStats.profitFactor}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-body text-gray-600 dark:text-gray-400">Total Trades</span>
                  <span className="text-body font-medium">{overallStats.totalTrades}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-body text-gray-600 dark:text-gray-400">Avg Trade Profit</span>
                  <span className="text-body font-medium">${overallStats.avgTradeProfit.toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-body text-gray-600 dark:text-gray-400">Best Month</span>
                  <span className="text-body font-medium text-ios-green">+18.5%</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-body text-gray-600 dark:text-gray-400">Worst Month</span>
                  <span className="text-body font-medium text-ios-red">-4.2%</span>
                </div>
              </div>
            </CollapsibleSection>
          </div>
        </motion.div>
      )}

      {activeTab === 'bySource' && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {Object.entries(sourcePerformance).map(([source, data]) => (
            <CollapsibleSection
              key={source}
              title={source}
              badge={`${(data.winRate * 100).toFixed(0)}% WR`}
              badgeType="success"
              defaultOpen={true}
              icon={<Activity className="w-5 h-5" />}
            >
              <div className="space-y-4">
                {/* Source Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="glass rounded-ios p-3">
                    <p className="text-caption text-gray-500 dark:text-gray-400">Total Profit</p>
                    <p className="text-headline font-medium mt-1">${data.totalProfit.toLocaleString()}</p>
                  </div>
                  <div className="glass rounded-ios p-3">
                    <p className="text-caption text-gray-500 dark:text-gray-400">Win Rate</p>
                    <p className="text-headline font-medium mt-1">{(data.winRate * 100).toFixed(1)}%</p>
                  </div>
                  <div className="glass rounded-ios p-3">
                    <p className="text-caption text-gray-500 dark:text-gray-400">Profit Factor</p>
                    <p className="text-headline font-medium mt-1">{data.profitFactor}</p>
                  </div>
                  <div className="glass rounded-ios p-3">
                    <p className="text-caption text-gray-500 dark:text-gray-400">Total Trades</p>
                    <p className="text-headline font-medium mt-1">{data.totalTrades}</p>
                  </div>
                </div>

                {/* Source Chart */}
                <PerformanceLineChart
                  data={data.data}
                  height={200}
                  type="line"
                />
              </div>
            </CollapsibleSection>
          ))}
        </motion.div>
      )}

      {activeTab === 'pareto' && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          <div className="ios-card p-4">
            <h3 className="text-headline mb-2">Pareto Principle Analysis</h3>
            <p className="text-body text-gray-600 dark:text-gray-400">
              The Pareto principle (80/20 rule) shows which strategies contribute most to your profits.
              Focus on optimizing your top performers.
            </p>
          </div>

          <ParetoScatterChart
            data={paretoData}
            title="Strategy Efficiency Analysis"
            height={400}
          />

          {/* Strategy Ranking */}
          <CollapsibleSection
            title="Strategy Ranking"
            icon={<Award className="w-5 h-5" />}
            defaultOpen={true}
          >
            <div className="space-y-3">
              {paretoData
                .sort((a, b) => b.efficiency - a.efficiency)
                .map((strategy, index) => (
                  <div
                    key={strategy.strategy}
                    className="flex items-center justify-between p-3 glass rounded-ios"
                  >
                    <div className="flex items-center gap-3">
                      <span className={clsx(
                        'w-8 h-8 rounded-full flex items-center justify-center text-caption font-bold',
                        index === 0 ? 'bg-gold text-gray-900' :
                        index === 1 ? 'bg-gray-300 text-gray-900' :
                        index === 2 ? 'bg-orange-400 text-gray-900' :
                        'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                      )}>
                        {index + 1}
                      </span>
                      <div>
                        <p className="text-body font-medium">{strategy.strategy}</p>
                        <p className="text-caption text-gray-500 dark:text-gray-400">
                          {strategy.trades} trades
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-body font-medium">${strategy.profit.toLocaleString()}</p>
                      <p className="text-caption text-gold">
                        {strategy.efficiency.toFixed(2)} $/trade
                      </p>
                    </div>
                  </div>
                ))}
            </div>
          </CollapsibleSection>
        </motion.div>
      )}
    </motion.div>
  );
};

export default Performance;