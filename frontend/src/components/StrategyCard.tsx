import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ExternalLink, TrendingUp, Target, Activity, BarChart3, Zap } from 'lucide-react';
import clsx from 'clsx';

interface StrategyData {
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
}

interface StrategyCardProps {
  strategy: StrategyData;
  onViewDetails?: (strategy: StrategyData) => void;
  className?: string;
}

const StrategyCard: React.FC<StrategyCardProps> = ({
  strategy,
  onViewDetails,
  className,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const phaseColors = {
    'I': 'badge-phase-i',
    'II': 'badge-phase-ii',
    'III': 'badge-phase-iii',
  };

  const statusColors = {
    active: 'bg-ios-green/10 text-ios-green',
    optimizing: 'bg-gold/10 text-gold',
    paused: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
  };

  const winRateColor =
    strategy.win_rate >= 65 ? 'text-success' :
    strategy.win_rate >= 50 ? 'text-warning' : 'text-danger';

  const rrColor =
    strategy.risk_reward >= 2.0 ? 'text-success' :
    strategy.risk_reward >= 1.5 ? 'text-warning' : 'text-danger';

  const evColor =
    strategy.expected_value > 0 ? 'text-success' : 'text-danger';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      whileHover={{ y: -4 }}
      className={clsx('card-ios overflow-hidden', className)}
    >
      {/* Header */}
      <div className="p-5 pb-0">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-headline text-gray-900 dark:text-gray-50">
                {strategy.webhook_source}
              </h3>
              <span className={clsx('badge-ios', phaseColors[strategy.phase])}>
                Phase {strategy.phase}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className={clsx('badge-ios text-[10px]', statusColors[strategy.status])}>
                {strategy.status === 'active' && (
                  <div className="w-1.5 h-1.5 bg-ios-green rounded-full animate-pulse mr-1" />
                )}
                {strategy.status}
              </span>
              <span className="text-caption text-gray-500 dark:text-gray-400">
                {strategy.total_trades} trades analyzed
              </span>
            </div>
          </div>

          {strategy.optimization_url && (
            <a
              href={strategy.optimization_url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 rounded-ios hover:glass transition-colors duration-200"
              aria-label="View in Optuna"
            >
              <ExternalLink className="w-4 h-4 text-gold" />
            </a>
          )}
        </div>

        {/* Key Metrics Grid */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          {/* Win Rate */}
          <div className="glass rounded-ios p-3 text-center">
            <div className={clsx('text-title2 font-bold', winRateColor)}>
              {strategy.win_rate.toFixed(0)}%
            </div>
            <div className="text-caption text-gray-500 dark:text-gray-400 mt-0.5">
              Win Rate
            </div>
          </div>

          {/* Risk/Reward */}
          <div className="glass rounded-ios p-3 text-center">
            <div className={clsx('text-title2 font-bold', rrColor)}>
              {strategy.risk_reward.toFixed(1)}
            </div>
            <div className="text-caption text-gray-500 dark:text-gray-400 mt-0.5">
              R/R Ratio
            </div>
          </div>

          {/* Expected Value */}
          <div className="glass rounded-ios p-3 text-center">
            <div className={clsx('text-title2 font-bold', evColor)}>
              {strategy.expected_value > 0 ? '+' : ''}{strategy.expected_value.toFixed(1)}%
            </div>
            <div className="text-caption text-gray-500 dark:text-gray-400 mt-0.5">
              EV
            </div>
          </div>
        </div>

        {/* Confidence Progress Bar */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-caption text-gray-600 dark:text-gray-300">
              Confidence Score
            </span>
            <span className="text-caption font-semibold text-gold">
              {strategy.confidence.toFixed(0)}%
            </span>
          </div>
          <div className="h-2 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${strategy.confidence}%` }}
              transition={{ duration: 1, ease: 'easeOut' }}
              className="h-full bg-gradient-to-r from-gold to-gold-light"
            />
          </div>
        </div>

        {/* TP/SL Display */}
        {(strategy.tp_percentage || strategy.sl_percentage) && (
          <div className="flex items-center gap-4 pb-4">
            {strategy.tp_percentage && (
              <div className="flex items-center gap-1.5">
                <Target className="w-3.5 h-3.5 text-success" />
                <span className="text-caption text-gray-600 dark:text-gray-300">
                  TP: {strategy.tp_percentage.toFixed(1)}%
                </span>
              </div>
            )}
            {strategy.sl_percentage && (
              <div className="flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-danger" />
                <span className="text-caption text-gray-600 dark:text-gray-300">
                  SL: {strategy.sl_percentage.toFixed(1)}%
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Expandable Details Button */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-5 py-3 glass hover:glass-strong transition-all duration-200
                   border-t border-gray-200/50 dark:border-gray-800/50
                   flex items-center justify-between group"
      >
        <span className="text-caption font-medium text-gray-600 dark:text-gray-300">
          View Details
        </span>
        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown className="w-4 h-4 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300" />
        </motion.div>
      </button>

      {/* Expanded Details */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 pt-3 space-y-4 border-t border-gray-200/50 dark:border-gray-800/50">
              {/* Trade Statistics */}
              <div className="grid grid-cols-2 gap-3">
                <div className="glass rounded-ios p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <TrendingUp className="w-3.5 h-3.5 text-success" />
                    <span className="text-caption text-gray-600 dark:text-gray-300">
                      Winning Trades
                    </span>
                  </div>
                  <p className="text-body font-semibold text-gray-900 dark:text-gray-50">
                    {strategy.profitable_trades} / {strategy.total_trades}
                  </p>
                </div>

                {strategy.avg_trade_duration && (
                  <div className="glass rounded-ios p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Zap className="w-3.5 h-3.5 text-gold" />
                      <span className="text-caption text-gray-600 dark:text-gray-300">
                        Avg Duration
                      </span>
                    </div>
                    <p className="text-body font-semibold text-gray-900 dark:text-gray-50">
                      {strategy.avg_trade_duration}
                    </p>
                  </div>
                )}
              </div>

              {/* Performance Sparkline (placeholder) */}
              {strategy.performance_trend && (
                <div className="glass rounded-ios p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 className="w-3.5 h-3.5 text-gold" />
                    <span className="text-caption text-gray-600 dark:text-gray-300">
                      Recent Performance
                    </span>
                  </div>
                  <div className="h-12 flex items-end gap-1">
                    {strategy.performance_trend.map((value, index) => (
                      <motion.div
                        key={index}
                        initial={{ height: 0 }}
                        animate={{ height: `${value}%` }}
                        transition={{ duration: 0.5, delay: index * 0.05 }}
                        className={clsx(
                          'flex-1 rounded-t',
                          value >= 0 ? 'bg-success' : 'bg-danger'
                        )}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex gap-2">
                {onViewDetails && (
                  <button
                    onClick={() => onViewDetails(strategy)}
                    className="btn-ios-primary flex-1"
                  >
                    <BarChart3 className="w-4 h-4" />
                    View Analysis
                  </button>
                )}
                {strategy.optimization_url && (
                  <a
                    href={strategy.optimization_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-ios-secondary flex-1"
                  >
                    <ExternalLink className="w-4 h-4" />
                    Optuna Dashboard
                  </a>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default React.memo(StrategyCard);