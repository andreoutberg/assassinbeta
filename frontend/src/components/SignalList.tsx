import React, { useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SignalCard } from './SignalCard';
import { EmptyState } from './EmptyState';
import { LoadingSpinner } from './LoadingSpinner';
import { TrendingUp } from 'lucide-react';
import clsx from 'clsx';

interface Signal {
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

interface SignalListProps {
  signals: Signal[];
  loading?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  onSignalClick?: (signal: Signal) => void;
  emptyMessage?: string;
  className?: string;
  variant?: 'default' | 'compact';
}

export const SignalList: React.FC<SignalListProps> = ({
  signals,
  loading = false,
  hasMore = false,
  onLoadMore,
  onSignalClick,
  emptyMessage = 'No signals found',
  className,
  variant = 'default',
}) => {
  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Infinite scroll setup
  useEffect(() => {
    if (!hasMore || !onLoadMore) return;

    const options = {
      root: null,
      rootMargin: '100px',
      threshold: 0.1,
    };

    observerRef.current = new IntersectionObserver((entries) => {
      const [entry] = entries;
      if (entry.isIntersecting && hasMore && !loading) {
        onLoadMore();
      }
    }, options);

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current);
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [hasMore, loading, onLoadMore]);

  // Loading skeleton
  const renderSkeleton = () => (
    <div className="space-y-3">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="card-ios p-4">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <div className="skeleton h-5 w-24 rounded" />
              <div className="skeleton h-3 w-32 rounded" />
            </div>
            <div className="space-y-2 text-right">
              <div className="skeleton h-5 w-16 rounded ml-auto" />
              <div className="skeleton h-3 w-12 rounded ml-auto" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  if (loading && signals.length === 0) {
    return (
      <div className={className}>
        {renderSkeleton()}
      </div>
    );
  }

  if (!loading && signals.length === 0) {
    return (
      <EmptyState
        icon={TrendingUp}
        message={emptyMessage}
        className={className}
      />
    );
  }

  return (
    <div className={clsx('space-y-3', className)}>
      <AnimatePresence mode="popLayout">
        {signals.map((signal, index) => (
          <motion.div
            key={signal.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{
              duration: 0.3,
              delay: index * 0.05,
            }}
          >
            <SignalCard
              signal={signal}
              onClick={onSignalClick}
            />
          </motion.div>
        ))}
      </AnimatePresence>

      {/* Load more trigger */}
      {hasMore && (
        <div ref={loadMoreRef} className="py-4">
          {loading ? (
            <div className="flex justify-center">
              <LoadingSpinner size="sm" />
            </div>
          ) : (
            <div className="text-center text-caption text-gray-500 dark:text-gray-400">
              Scroll to load more...
            </div>
          )}
        </div>
      )}
    </div>
  );
};