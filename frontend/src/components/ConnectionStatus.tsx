import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Wifi, WifiOff } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import clsx from 'clsx';

interface ConnectionStatusProps {
  isConnected: boolean;
  connectionTime?: Date | null;
  className?: string;
  variant?: 'compact' | 'full';
}

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({
  isConnected,
  connectionTime,
  className,
  variant = 'compact',
}) => {
  const getUptime = () => {
    if (!connectionTime) return '';
    return formatDistanceToNow(connectionTime, { addSuffix: false });
  };

  if (variant === 'compact') {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        className={clsx(
          'flex items-center gap-2 px-3 py-1.5 rounded-full glass',
          className
        )}
      >
        <AnimatePresence mode="wait">
          {isConnected ? (
            <motion.div
              key="connected"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              className="relative"
            >
              <Wifi className="w-4 h-4 text-ios-green" />
              <div className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-ios-green rounded-full">
                <div className="absolute inset-0 bg-ios-green rounded-full animate-ping" />
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="disconnected"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
            >
              <WifiOff className="w-4 h-4 text-danger animate-pulse" />
            </motion.div>
          )}
        </AnimatePresence>

        <span className={clsx(
          'text-caption font-medium',
          isConnected ? 'text-ios-green' : 'text-danger'
        )}>
          {isConnected ? 'Live' : 'Offline'}
        </span>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'card-ios p-4',
        isConnected && 'border-ios-green/30',
        !isConnected && 'border-danger/30',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={clsx(
            'p-2.5 rounded-ios',
            isConnected ? 'bg-ios-green/10' : 'bg-danger/10'
          )}>
            {isConnected ? (
              <Wifi className="w-5 h-5 text-ios-green" />
            ) : (
              <WifiOff className="w-5 h-5 text-danger" />
            )}
          </div>

          <div>
            <p className={clsx(
              'text-headline',
              isConnected ? 'text-ios-green' : 'text-danger'
            )}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </p>
            {isConnected && connectionTime && (
              <p className="text-caption text-gray-500 dark:text-gray-400 mt-0.5">
                Uptime: {getUptime()}
              </p>
            )}
          </div>
        </div>

        {isConnected && (
          <div className="relative">
            <div className="w-3 h-3 bg-ios-green rounded-full">
              <div className="absolute inset-0 bg-ios-green rounded-full animate-ping" />
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
};