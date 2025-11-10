import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { motion } from 'framer-motion';
import clsx from 'clsx';

interface DarkModeToggleProps {
  className?: string;
}

const DarkModeToggle: React.FC<DarkModeToggleProps> = ({ className }) => {
  const [isDark, setIsDark] = React.useState(false);

  React.useEffect(() => {
    const isDarkMode = document.documentElement.classList.contains('dark');
    setIsDark(isDarkMode);
  }, []);

  const toggleDarkMode = () => {
    const newDarkMode = !isDark;
    setIsDark(newDarkMode);

    if (newDarkMode) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  };

  return (
    <button
      onClick={toggleDarkMode}
      className={clsx(
        'relative inline-flex h-7 w-14 items-center rounded-full',
        'bg-gray-300 dark:bg-gray-700 transition-colors duration-200',
        'focus:outline-none focus:ring-2 focus:ring-gold/50',
        className
      )}
      aria-label="Toggle dark mode"
    >
      <motion.span
        className={clsx(
          'inline-block h-6 w-6 transform rounded-full bg-white',
          'transition-transform duration-200 shadow-sm',
          'flex items-center justify-center'
        )}
        animate={{ x: isDark ? 28 : 2 }}
        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      >
        {isDark ? (
          <Moon className="w-3.5 h-3.5 text-gray-700" />
        ) : (
          <Sun className="w-3.5 h-3.5 text-yellow-500" />
        )}
      </motion.span>
    </button>
  );
};

export default DarkModeToggle;