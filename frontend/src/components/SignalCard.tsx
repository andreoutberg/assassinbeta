import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, TrendingUp, TrendingDown, Clock, Target, StopCircle, DollarSign } from 'lucide-react';
import clsx from 'clsx';
import { format } from 'date-fns';

interface SignalData {
  id: string;
  symbol: string;
  direction: 'LONG' | 'SHORT';
  entry_price: number;
  current_price?: number;
  tp_price?: number;
  sl_price?: number;
  pnl?: number;
  pnl_percentage?: number;
  phase: 'I' | 'II' | 'III';
  webhook_source: string;
  timestamp: Date | string;
  status: 'active' | 'closed' | 'pending';
  volume?: number;
  confidence?: number;
  risk_reward?: number;
}

interface SignalCardProps {
  signal: SignalData;
  isActive?: boolean;
  onClick?: (signal: SignalData) => void;
}

export const SignalCard: React.FC<SignalCardProps> = ({
  signal,
  isActive = false,
  onClick,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleClick = () => {
    if (onClick) {
      onClick(signal);
    } else {
      setIsExpanded(!isExpanded);
    }
  };

  const pnlColor = (signal.pnl || 0) >= 0 ? 'text-success' : 'text-danger';
  const DirectionIcon = signal.direction === 'LONG' ? TrendingUp : TrendingDown;

  const phaseColors = {
    'I': 'badge-phase-i',
    'II': 'badge-phase-ii',
    'III': 'badge-phase-iii',
  };

  const statusColors = {
    active: 'bg-ios-green/10 text-ios-green border-ios-green/20',
    closed: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
    pending: 'bg-gold/10 text-gold border-gold/20',
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'card-ios overflow-hidden',
        isActive && 'ring-2 ring-gold glow-gold',
        'transition-all duration-200'
      )}
    >
      <button
        onClick={handleClick}
        className="w-full px-4 py-3 md:px-5 md:py-4 touch-feedback focus-ring"
      >
        {/* Main content */}
        <div className="flex items-center justify-between gap-3">
          {/* Left side - Symbol and direction */}
          <div className="flex items-center gap-3 min-w-0">
            <div className={clsx(
              'p-2 rounded-ios',
              signal.direction === 'LONG'
                ? 'bg-success/10 text-success'
                : 'bg-danger/10 text-danger'
            )}>
              <DirectionIcon className="w-4 h-4" />
            </div>

            <div className="text-left min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-headline text-gray-900 dark:text-gray-50">
                  {signal.symbol}
                </h3>
                <span className={clsx('badge-ios text-[10px]', phaseColors[signal.phase])}>
                  Phase {signal.phase}
                </span>
              </div>

              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-caption text-gray-500 dark:text-gray-400">
                  {signal.webhook_source}
                </span>
                <span className="text-caption text-gray-400">•</span>
                <span className="text-caption text-gray-500 dark:text-gray-400">
                  ${signal.entry_price.toFixed(2)}
                </span>
              </div>
            </div>
          </div>

          {/* Right side - P&L and status */}
          <div className="flex items-center gap-3">
            {/* P&L Display */}
            {signal.pnl !== undefined && (
              <div className="text-right">
                <div className={clsx('text-headline font-semibold', pnlColor)}>
                  {signal.pnl >= 0 ? '+' : ''}{signal.pnl_percentage?.toFixed(1)}%
                </div>
                <div className={clsx('text-caption', pnlColor)}>
                  ${Math.abs(signal.pnl).toFixed(2)}
                </div>
              </div>
            )}

            {/* Status badge */}
            <div className={clsx(
              'badge-ios',
              statusColors[signal.status]
            )}>
              {signal.status === 'active' && (
                <div className="w-1.5 h-1.5 bg-ios-green rounded-full animate-pulse mr-1" />
              )}
              <span className="text-[10px] uppercase font-semibold">
                {signal.status}
              </span>
            </div>

            {/* Expand chevron */}
            {!onClick && (
              <motion.div
                animate={{ rotate: isExpanded ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <ChevronDown className="w-4 h-4 text-gray-400" />
              </motion.div>
            )}
          </div>
        </div>
      </button>

      {/* Expanded details */}
      <AnimatePresence>
        {isExpanded && !onClick && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-2 md:px-5 md:pb-5 border-t border-gray-200/50 dark:border-gray-800/50">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {/* Entry info */}
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-caption text-gray-500">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Entry</span>
                  </div>
                  <p className="text-body font-medium text-gray-900 dark:text-gray-50">
                    ${signal.entry_price.toFixed(2)}
                  </p>
                </div>

                {/* TP info */}
                {signal.tp_price && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-caption text-success">
                      <Target className="w-3.5 h-3.5" />
                      <span>Take Profit</span>
                    </div>
                    <p className="text-body font-medium text-gray-900 dark:text-gray-50">
                      ${signal.tp_price.toFixed(2)}
                    </p>
                  </div>
                )}

                {/* SL info */}
                {signal.sl_price && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-caption text-danger">
                      <StopCircle className="w-3.5 h-3.5" />
                      <span>Stop Loss</span>
                    </div>
                    <p className="text-body font-medium text-gray-900 dark:text-gray-50">
                      ${signal.sl_price.toFixed(2)}
                    </p>
                  </div>
                )}

                {/* R/R info */}
                {signal.risk_reward && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-caption text-gold">
                      <DollarSign className="w-3.5 h-3.5" />
                      <span>R/R Ratio</span>
                    </div>
                    <p className="text-body font-medium text-gray-900 dark:text-gray-50">
                      {signal.risk_reward.toFixed(2)}:1
                    </p>
                  </div>
                )}
              </div>

              {/* Timestamp */}
              <div className="mt-3 pt-3 border-t border-gray-200/50 dark:border-gray-800/50">
                <p className="text-caption text-gray-500 dark:text-gray-400">
                  {format(new Date(signal.timestamp), 'MMM dd, yyyy • HH:mm:ss')}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};