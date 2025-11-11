import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, Layers, BarChart3, DollarSign, Activity, Target, ExternalLink, Database } from 'lucide-react';
import StatCard from '../components/StatCard';
import { CollapsibleSection } from '../components/CollapsibleSection';
import StrategyCard from '../components/StrategyCard';
import { WinRateGauge } from '../components/Charts/WinRateGauge';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { useSignals } from '../hooks/useSignals';
import { useStrategies } from '../hooks/useStrategies';
import { useStats } from '../hooks/useStats';
import clsx from 'clsx';

export const Home: React.FC = () => {
  const { data: signalsData, isLoading: signalsLoading } = useSignals({ limit: 10 });
  const { data: strategiesData, isLoading: strategiesLoading } = useStrategies();
  const { data: statsData, isLoading: statsLoading } = useStats();

  const isLoading = signalsLoading || strategiesLoading || statsLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner size="lg" text="Loading dashboard..." />
      </div>
    );
  }

  const stats = (statsData as any) || { total_signals: 0, active_strategies: 0, overall_win_rate: 0, total_pnl: 0 };
  const signals = (signalsData as any)?.trades || [];
  const strategies = (strategiesData as any[]) || [];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6"
      >
        <h1 className="text-[28px] font-semibold text-white mb-1">
          Overview
        </h1>
        <p className="text-[15px] text-gray-400">
          Real-time trading metrics and market summary
        </p>
      </motion.div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          value={(signalsData as any)?.count || signals.length}
          label="Active Trades"
          icon={TrendingUp}
          color="blue"
        />
        <StatCard
          value={strategies.length}
          label="Active Strategies"
          icon={Layers}
          color="gold"
        />
        <StatCard
          value={stats.overall_win_rate ? `${stats.overall_win_rate.toFixed(1)}%` : "N/A"}
          label="Win Rate"
          icon={Target}
          color="success"
        />
        <StatCard
          value={stats.total_pnl ? `$${stats.total_pnl.toLocaleString()}` : "$0"}
          label="Total P&L"
          icon={DollarSign}
          color={stats.total_pnl >= 0 ? 'success' : 'danger'}
        />
      </div>

      {/* Quick Stats Section */}
      {stats.overall_win_rate !== undefined && (
        <CollapsibleSection
          title="Performance Overview"
          summary={`Win Rate: ${stats.overall_win_rate?.toFixed(1)}% | ${signals.length} Active Trades`}
          defaultOpen={true}
          icon={BarChart3}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Win Rate Gauge */}
            <div className="card-dark p-6 flex items-center justify-center">
              <WinRateGauge
                value={stats.overall_win_rate || 0}
                size="md"
              />
            </div>

            {/* Trade Summary */}
            <div className="space-y-4">
              <div className="card-dark p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[13px] text-gray-400">
                    Active Trades
                  </span>
                  <span className="text-[17px] font-semibold text-white">
                    {signals.length}
                  </span>
                </div>
              </div>

              <div className="card-dark p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[13px] text-gray-400">
                    Total P&L
                  </span>
                  <span className={clsx(
                    'text-[17px] font-semibold',
                    stats.total_pnl >= 0 ? 'text-ios-green' : 'text-ios-red'
                  )}>
                    {stats.total_pnl >= 0 ? '+' : ''}${stats.total_pnl?.toFixed(2) || '0.00'}
                  </span>
                </div>
              </div>

              <div className="card-dark p-4">
                <div className="flex items-center gap-3">
                  <Activity className="w-5 h-5 text-gold" />
                  <div className="flex-1">
                    <p className="text-[11px] text-gray-400">
                      Trading Status
                    </p>
                    <p className="text-[15px] font-semibold text-white">
                      {signals.length > 0 ? 'Active' : 'Idle'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </CollapsibleSection>
      )}

      {/* Recent Signals */}
      <CollapsibleSection
        title="Active Trades"
        summary={`${signals.length} active trades`}
        defaultOpen={true}
        icon={TrendingUp}
        badge={
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 bg-ios-green rounded-full animate-pulse" />
            <span className="text-[11px] text-ios-green">Live</span>
          </div>
        }
      >
        <div className="space-y-3">
          {signals.length > 0 ? (
            signals.slice(0, 5).map((trade: any) => (
              <div key={trade.id} className="card-dark p-4 rounded-[12px]">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[15px] font-semibold text-white">{trade.symbol}</span>
                    <span className={clsx(
                      "text-[11px] px-2 py-0.5 rounded-full",
                      trade.direction === 'LONG' ? "bg-ios-green/20 text-ios-green" : "bg-ios-red/20 text-ios-red"
                    )}>
                      {trade.direction}
                    </span>
                  </div>
                  <span className={clsx(
                    "text-[15px] font-bold",
                    trade.current_pnl_pct >= 0 ? "text-ios-green" : "text-ios-red"
                  )}>
                    {trade.current_pnl_pct >= 0 ? '+' : ''}{trade.current_pnl_pct?.toFixed(2)}%
                  </span>
                </div>
                <div className="flex items-center justify-between text-[13px] text-gray-400">
                  <span>Entry: ${trade.entry_price}</span>
                  <span>Current: ${trade.current_price}</span>
                </div>
              </div>
            ))
          ) : (
            <p className="text-gray-400 text-center py-8">No active trades</p>
          )}
        </div>
      </CollapsibleSection>

      {/* Active Strategies */}
      <CollapsibleSection
        title="Active Strategies"
        summary={`${strategies.length} strategies active`}
        defaultOpen={false}
        icon={Layers}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {strategies.length > 0 ? (
            strategies.slice(0, 4).map((strategy: any) => (
              <StrategyCard key={strategy.id} strategy={strategy} />
            ))
          ) : (
            <p className="text-gray-400 text-center py-8 col-span-2">No active strategies</p>
          )}
        </div>
      </CollapsibleSection>

      {/* Monitoring Tools */}
      <CollapsibleSection
        title="Monitoring Tools"
        summary="Quick access to system monitoring and optimization"
        defaultOpen={true}
        icon={Activity}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Optuna Dashboard */}
          <motion.a
            href="/optuna/"
            target="_blank"
            rel="noopener noreferrer"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="card-dark p-5 rounded-[12px] group hover:border-gold/50 border border-transparent transition-all duration-300"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="p-2.5 rounded-[10px] bg-ios-blue/10">
                <BarChart3 className="w-5 h-5 text-ios-blue" />
              </div>
              <ExternalLink className="w-4 h-4 text-gray-500 group-hover:text-gold transition-colors" />
            </div>
            <h3 className="text-[15px] font-semibold text-white mb-1.5">Optuna Dashboard</h3>
            <p className="text-[13px] text-gray-400 leading-relaxed">
              Strategy optimization & hyperparameter tuning
            </p>
            <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-800">
              <div className="w-1.5 h-1.5 rounded-full bg-ios-green animate-pulse" />
              <span className="text-[11px] text-gray-500">Port 8080</span>
            </div>
          </motion.a>

          {/* Grafana */}
          <motion.a
            href="/grafana/"
            target="_blank"
            rel="noopener noreferrer"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="card-dark p-5 rounded-[12px] group hover:border-gold/50 border border-transparent transition-all duration-300"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="p-2.5 rounded-[10px] bg-orange-500/10">
                <Activity className="w-5 h-5 text-orange-500" />
              </div>
              <ExternalLink className="w-4 h-4 text-gray-500 group-hover:text-gold transition-colors" />
            </div>
            <h3 className="text-[15px] font-semibold text-white mb-1.5">Grafana</h3>
            <p className="text-[13px] text-gray-400 leading-relaxed">
              System metrics & performance monitoring
            </p>
            <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-800">
              <div className="w-1.5 h-1.5 rounded-full bg-ios-green animate-pulse" />
              <span className="text-[11px] text-gray-500">Port 3001</span>
            </div>
          </motion.a>

          {/* Prometheus */}
          <motion.a
            href="/prometheus/"
            target="_blank"
            rel="noopener noreferrer"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="card-dark p-5 rounded-[12px] group hover:border-gold/50 border border-transparent transition-all duration-300"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="p-2.5 rounded-[10px] bg-ios-red/10">
                <Database className="w-5 h-5 text-ios-red" />
              </div>
              <ExternalLink className="w-4 h-4 text-gray-500 group-hover:text-gold transition-colors" />
            </div>
            <h3 className="text-[15px] font-semibold text-white mb-1.5">Prometheus</h3>
            <p className="text-[13px] text-gray-400 leading-relaxed">
              Metrics collection & time-series database
            </p>
            <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-800">
              <div className="w-1.5 h-1.5 rounded-full bg-ios-green animate-pulse" />
              <span className="text-[11px] text-gray-500">Port 9090</span>
            </div>
          </motion.a>
        </div>
      </CollapsibleSection>
    </div>
  );
};