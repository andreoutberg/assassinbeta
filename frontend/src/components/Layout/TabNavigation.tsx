import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Home, TrendingUp, Layers, BarChart3 } from 'lucide-react';
import clsx from 'clsx';

interface Tab {
  path: string;
  label: string;
  icon: React.FC<{ className?: string }>;
}

const tabs: Tab[] = [
  { path: '/', label: 'Home', icon: Home },
  { path: '/signals', label: 'Signals', icon: TrendingUp },
  { path: '/strategies', label: 'Strategies', icon: Layers },
  { path: '/performance', label: 'Performance', icon: BarChart3 },
];

export const TabNavigation: React.FC = () => {
  const location = useLocation();

  return (
    <nav className="relative">
      <div className="flex items-center justify-around md:justify-start md:gap-1 py-2 md:py-0">
        {tabs.map((tab) => {
          const isActive = location.pathname === tab.path ||
            (tab.path !== '/' && location.pathname.startsWith(tab.path));
          const Icon = tab.icon;

          return (
            <Link
              key={tab.path}
              to={tab.path}
              className={clsx(
                'relative flex flex-col md:flex-row items-center justify-center md:justify-start',
                'gap-1 md:gap-2 px-3 md:px-5 py-2 md:py-3',
                'min-w-0 flex-1 md:flex-initial',
                'transition-all duration-200 rounded-ios',
                'hover:bg-gray-100 dark:hover:bg-gray-800',
                'touch-feedback focus-ring',
                isActive && 'text-gold'
              )}
            >
              <Icon className={clsx(
                'w-5 h-5 md:w-4 md:h-4 transition-colors duration-200',
                isActive ? 'text-gold' : 'text-gray-500 dark:text-gray-400'
              )} />

              <span className={clsx(
                'text-caption md:text-body font-medium transition-colors duration-200',
                isActive ? 'text-gold' : 'text-gray-600 dark:text-gray-300'
              )}>
                {tab.label}
              </span>

              {/* Active indicator for desktop */}
              {isActive && (
                <motion.div
                  layoutId="activeTab"
                  className="hidden md:block absolute bottom-0 left-3 right-3 h-0.5 bg-gold"
                  initial={false}
                  transition={{
                    type: 'spring',
                    stiffness: 500,
                    damping: 30
                  }}
                />
              )}

              {/* Active dot for mobile */}
              {isActive && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="md:hidden absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 bg-gold rounded-full"
                />
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
};