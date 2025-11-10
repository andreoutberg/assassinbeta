import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Activity, Filter, TrendingUp, AlertCircle, Clock } from 'lucide-react';
import FilterBar from '../components/FilterBar';
import SignalCard from '../components/SignalCard';
import CollapsibleSection from '../components/CollapsibleSection';
import PhaseIndicator from '../components/PhaseIndicator';
import clsx from 'clsx';

interface Signal {
  id: string;
  timestamp: Date;
  symbol: string;
  source: string;
  signal_type: 'BUY' | 'SELL' | 'HOLD';
  strength: number;
  price: number;
  target: number;
  stop_loss: number;
  confidence: number;
  metadata?: {
    volume?: number;
    rsi?: number;
    phase?: string;
  };
}

const Signals: React.FC = () => {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [filteredSignals, setFilteredSignals] = useState<Signal[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>('all');
  const [selectedType, setSelectedType] = useState<string>('all');
  const [selectedStrength, setSelectedStrength] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  // Mock data for demonstration
  useEffect(() => {
    const mockSignals: Signal[] = [
      {
        id: '1',
        timestamp: new Date(),
        symbol: 'BTC/USD',
        source: 'Ichimoku',
        signal_type: 'BUY',
        strength: 0.85,
        price: 95000,
        target: 98000,
        stop_loss: 93000,
        confidence: 0.82,
        metadata: {
          volume: 1250000,
          rsi: 55,
          phase: 'markup',
        },
      },
      {
        id: '2',
        timestamp: new Date(Date.now() - 3600000),
        symbol: 'ETH/USD',
        source: 'Wyckoff',
        signal_type: 'SELL',
        strength: 0.72,
        price: 3200,
        target: 3000,
        stop_loss: 3300,
        confidence: 0.75,
        metadata: {
          volume: 850000,
          rsi: 68,
          phase: 'distribution',
        },
      },
      {
        id: '3',
        timestamp: new Date(Date.now() - 7200000),
        symbol: 'SOL/USD',
        source: 'SmartMoney',
        signal_type: 'BUY',
        strength: 0.91,
        price: 145,
        target: 160,
        stop_loss: 140,
        confidence: 0.88,
        metadata: {
          volume: 450000,
          rsi: 42,
          phase: 'accumulation',
        },
      },
    ];
    setSignals(mockSignals);
    setFilteredSignals(mockSignals);
    setLoading(false);
  }, []);

  // Filter signals
  useEffect(() => {
    let filtered = [...signals];

    if (selectedSource !== 'all') {
      filtered = filtered.filter(s => s.source === selectedSource);
    }

    if (selectedType !== 'all') {
      filtered = filtered.filter(s => s.signal_type === selectedType);
    }

    if (selectedStrength !== 'all') {
      const threshold = parseFloat(selectedStrength);
      filtered = filtered.filter(s => s.strength >= threshold);
    }

    setFilteredSignals(filtered);
  }, [selectedSource, selectedType, selectedStrength, signals]);

  const sources = ['all', 'Ichimoku', 'Wyckoff', 'SmartMoney'];
  const types = ['all', 'BUY', 'SELL', 'HOLD'];
  const strengths = [
    { value: 'all', label: 'All Strengths' },
    { value: '0.5', label: '≥ 50%' },
    { value: '0.7', label: '≥ 70%' },
    { value: '0.85', label: '≥ 85%' },
  ];

  const getSignalStats = () => {
    const totalSignals = filteredSignals.length;
    const buySignals = filteredSignals.filter(s => s.signal_type === 'BUY').length;
    const sellSignals = filteredSignals.filter(s => s.signal_type === 'SELL').length;
    const avgStrength = filteredSignals.reduce((acc, s) => acc + s.strength, 0) / totalSignals || 0;

    return {
      total: totalSignals,
      buy: buySignals,
      sell: sellSignals,
      avgStrength: (avgStrength * 100).toFixed(1),
    };
  };

  const stats = getSignalStats();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold"></div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-largeTitle font-bold gold-gradient-text">Trading Signals</h1>
          <p className="text-body text-gray-600 dark:text-gray-400 mt-1">
            Real-time signals from multiple strategies
          </p>
        </div>
        <PhaseIndicator phase="analyzing" confidence={0.85} size="lg" />
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="ios-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-caption text-gray-500 dark:text-gray-400">Total Signals</p>
              <p className="text-title2 font-bold mt-1">{stats.total}</p>
            </div>
            <Activity className="w-6 h-6 text-gold" />
          </div>
        </div>

        <div className="ios-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-caption text-gray-500 dark:text-gray-400">Buy Signals</p>
              <p className="text-title2 font-bold text-ios-green mt-1">{stats.buy}</p>
            </div>
            <TrendingUp className="w-6 h-6 text-ios-green" />
          </div>
        </div>

        <div className="ios-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-caption text-gray-500 dark:text-gray-400">Sell Signals</p>
              <p className="text-title2 font-bold text-ios-red mt-1">{stats.sell}</p>
            </div>
            <AlertCircle className="w-6 h-6 text-ios-red" />
          </div>
        </div>

        <div className="ios-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-caption text-gray-500 dark:text-gray-400">Avg Strength</p>
              <p className="text-title2 font-bold mt-1">{stats.avgStrength}%</p>
            </div>
            <Clock className="w-6 h-6 text-ios-blue" />
          </div>
        </div>
      </div>

      {/* Filters */}
      <CollapsibleSection
        title="Filters"
        icon={<Filter className="w-5 h-5" />}
        defaultOpen={true}
        badge={filteredSignals.length !== signals.length ? 'Active' : undefined}
        badgeType="info"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-caption text-gray-600 dark:text-gray-400 mb-2 block">
                Source
              </label>
              <select
                value={selectedSource}
                onChange={(e) => setSelectedSource(e.target.value)}
                className="ios-input w-full"
              >
                {sources.map(source => (
                  <option key={source} value={source}>
                    {source === 'all' ? 'All Sources' : source}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-caption text-gray-600 dark:text-gray-400 mb-2 block">
                Signal Type
              </label>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="ios-input w-full"
              >
                {types.map(type => (
                  <option key={type} value={type}>
                    {type === 'all' ? 'All Types' : type}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-caption text-gray-600 dark:text-gray-400 mb-2 block">
                Minimum Strength
              </label>
              <select
                value={selectedStrength}
                onChange={(e) => setSelectedStrength(e.target.value)}
                className="ios-input w-full"
              >
                {strengths.map(strength => (
                  <option key={strength.value} value={strength.value}>
                    {strength.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </CollapsibleSection>

      {/* Signals List */}
      <div className="space-y-4">
        {filteredSignals.length > 0 ? (
          filteredSignals.map((signal, index) => (
            <motion.div
              key={signal.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <SignalCard
                signal={signal}
                onAction={(action) => console.log(`${action} signal ${signal.id}`)}
              />
            </motion.div>
          ))
        ) : (
          <div className="ios-card p-8 text-center">
            <Filter className="w-12 h-12 text-gray-400 mx-auto mb-3" />
            <p className="text-headline text-gray-600 dark:text-gray-400">
              No signals match your filters
            </p>
            <p className="text-body text-gray-500 dark:text-gray-500 mt-1">
              Try adjusting your filter criteria
            </p>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default Signals;