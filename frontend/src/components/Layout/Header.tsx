import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sun, Moon, Wifi, WifiOff } from 'lucide-react';
import { ConnectionStatus } from '../ConnectionStatus';

export const Header: React.FC = () => {
  const [isDark, setIsDark] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionTime, setConnectionTime] = useState<Date | null>(null);

  useEffect(() => {
    // Check for dark mode preference
    const darkMode = localStorage.getItem('darkMode') === 'true' ||
      (!localStorage.getItem('darkMode') && window.matchMedia('(prefers-color-scheme: dark)').matches);

    setIsDark(darkMode);
    if (darkMode) {
      document.documentElement.classList.add('dark');
    }

    // Simulated connection status - replace with actual WebSocket status
    const timeout = setTimeout(() => {
      setIsConnected(true);
      setConnectionTime(new Date());
    }, 1000);

    return () => clearTimeout(timeout);
  }, []);

  const toggleDarkMode = () => {
    const newMode = !isDark;
    setIsDark(newMode);
    localStorage.setItem('darkMode', String(newMode));

    if (newMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  return (
    <header className="sticky top-0 z-50 glass-strong border-b border-gray-200/50 dark:border-gray-800/50 safe-area-top">
      <div className="container mx-auto px-4 py-4 md:py-6">
        <div className="flex items-center justify-between">
          {/* Logo and Title */}
          <div className="flex items-center gap-4">
            <motion.div
              initial={{ scale: 0, rotate: -180 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ duration: 0.5, type: 'spring' }}
              className="relative"
            >
              <div className="w-10 h-10 md:w-12 md:h-12 rounded-ios bg-gradient-to-br from-gold via-gold-light to-gold flex items-center justify-center shadow-lg">
                <span className="text-white font-bold text-xl md:text-2xl">A</span>
              </div>
              {isConnected && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="absolute -top-1 -right-1 w-3 h-3 bg-ios-green rounded-full border-2 border-white dark:border-gray-900"
                >
                  <div className="absolute inset-0 bg-ios-green rounded-full animate-ping" />
                </motion.div>
              )}
            </motion.div>

            <div>
              <h1 className="text-largeTitle font-bold text-gray-900 dark:text-gray-50 text-sf">
                Andre Assassin
              </h1>
              <p className="text-caption text-gray-500 dark:text-gray-400 mt-0.5">
                BETA Trading Dashboard
              </p>
            </div>
          </div>

          {/* Right side actions */}
          <div className="flex items-center gap-2 md:gap-4">
            {/* Connection Status */}
            <ConnectionStatus
              isConnected={isConnected}
              connectionTime={connectionTime}
            />

            {/* Dark mode toggle */}
            <button
              onClick={toggleDarkMode}
              className="btn-ios-ghost p-2.5 md:p-3"
              aria-label="Toggle dark mode"
            >
              <AnimatePresence mode="wait">
                {isDark ? (
                  <motion.div
                    key="moon"
                    initial={{ scale: 0, rotate: -90 }}
                    animate={{ scale: 1, rotate: 0 }}
                    exit={{ scale: 0, rotate: 90 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Moon className="w-5 h-5 md:w-6 md:h-6 text-gold" />
                  </motion.div>
                ) : (
                  <motion.div
                    key="sun"
                    initial={{ scale: 0, rotate: 90 }}
                    animate={{ scale: 1, rotate: 0 }}
                    exit={{ scale: 0, rotate: -90 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Sun className="w-5 h-5 md:w-6 md:h-6 text-gold" />
                  </motion.div>
                )}
              </AnimatePresence>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};