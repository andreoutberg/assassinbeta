import React, { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { Header } from './Header';
import { TabNavigation } from './TabNavigation';

interface AppLayoutProps {
  children: ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  return (
    <div className="min-h-screen bg-black transition-colors">
      {/* Subtle background effect */}
      <div className="fixed inset-0 bg-gradient-to-br from-gray-900/20 via-transparent to-gray-900/20 pointer-events-none" />

      {/* Main container */}
      <div className="relative z-10 flex flex-col min-h-screen">
        {/* Header */}
        <Header />

        {/* Desktop: Top navigation */}
        <div className="hidden md:block sticky top-0 z-40 glass-strong border-b border-gray-800/50">
          <div className="container mx-auto px-6">
            <TabNavigation />
          </div>
        </div>

        {/* Main content */}
        <main className="flex-1 container mx-auto px-6 py-6 md:py-8 pb-20 md:pb-8">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
          >
            {children}
          </motion.div>
        </main>

        {/* Mobile: Bottom navigation */}
        <div className="md:hidden fixed bottom-0 left-0 right-0 z-40 glass-strong border-t border-gray-800/50 safe-area-bottom">
          <TabNavigation />
        </div>
      </div>
    </div>
  );
};