import React, { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Activity, TrendingUp, AlertCircle, Clock, Filter } from 'lucide-react';
import SignalCard from '../components/SignalCard';
import { CollapsibleSection } from '../components/CollapsibleSection';

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

const Signals: React.FC = () => {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>('all');
  const [selectedType, setSelectedType] = useState<string>('all');
  const [selectedStrength, setSelectedStrength] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  // Fetch real signals from API
  useEffect(() => {
    const fetchSignals = async () => {
      try {
        const baseUrl = `${window.location.protocol}//${window.location.hostname}`;
        const response = await fetch(`${baseUrl}/api/trades/active`);

        if (response.ok) {
          const data = await response.json();
          const trades = data.trades || [];

          // Map backend trades to Signal format
          const mappedSignals: Signal[] = trades.map((trade: any) => ({
            id: trade.id?.toString() || '',
            symbol: trade.symbol || '',
            direction: trade.direction || 'LONG',
            entry_price: trade.entry_price || 0,
            current_price: trade.current_price,
            tp_price: trade.take_profit_price,
            sl_price: trade.stop_loss_price,
            pnl: trade.current_pnl,
            pnl_percentage: trade.current_pnl_pct,
            phase: trade.phase || 'I',
            webhook_source: trade.webhook_source || 'Unknown',
            timestamp: trade.entry_timestamp || new Date(),
            status: 'active',
            confidence: 75,
            risk_reward: trade.risk_reward || 0,
          }));

          setSignals(mappedSignals);
        }
      } catch (error) {
        console.error('Failed to fetch signals:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchSignals();

    // Refresh every 30 seconds
    const interval = setInterval(fetchSignals, 30000);
    return () => clearInterval(interval);
  }, []);

  // Filter signals with useMemo
  const filteredSignals = useMemo(() => {
    let filtered = [...signals];

    if (selectedSource !== 'all') {
      filtered = filtered.filter(s => s.webhook_source === selectedSource);
    }

    if (selectedType !== 'all') {
      filtered = filtered.filter(s => s.direction === selectedType);
    }

    if (selectedStrength !== 'all') {
      const threshold = parseFloat(selectedStrength);
      filtered = filtered.filter(s => (s.confidence || 0) >= threshold);
    }

    return filtered;
  }, [selectedSource, selectedType, selectedStrength, signals]);

  // Get unique sources from signals
  const sources = useMemo(() => {
    const uniqueSources = Array.from(new Set(signals.map(s => s.webhook_source)));
    return ['all', ...uniqueSources];
  }, [signals]);

  const types = ['all', 'LONG', 'SHORT'];
  const strengths = [
    { value: 'all', label: 'All Confidence' },
    { value: '50', label: '≥ 50%' },
    { value: '70', label: '≥ 70%' },
    { value: '85', label: '≥ 85%' },
  ];

  const getSignalStats = () => {
    const totalSignals = filteredSignals.length;
    const buySignals = filteredSignals.filter(s => s.direction === 'LONG').length;
    const sellSignals = filteredSignals.filter(s => s.direction === 'SHORT').length;
    const avgStrength = filteredSignals.reduce((acc, s) => acc + (s.confidence || 0), 0) / totalSignals || 0;

    return {
      total: totalSignals,
      buy: buySignals,
      sell: sellSignals,
      avgStrength: avgStrength.toFixed(1),
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
      <div>
        <h1 className="text-[28px] font-semibold text-white mb-1">Trading Signals</h1>
        <p className="text-[15px] text-gray-400">Real-time trading signals from all sources</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card-dark p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-gold" />
            <span className="text-[11px] text-gray-400">Total Signals</span>
          </div>
          <p className="text-[24px] font-bold text-white">{stats.total}</p>
        </div>
        <div className="card-dark p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-ios-green" />
            <span className="text-[11px] text-gray-400">Long</span>
          </div>
          <p className="text-[24px] font-bold text-ios-green">{stats.buy}</p>
        </div>
        <div className="card-dark p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-ios-red rotate-180" />
            <span className="text-[11px] text-gray-400">Short</span>
          </div>
          <p className="text-[24px] font-bold text-ios-red">{stats.sell}</p>
        </div>
        <div className="card-dark p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-4 h-4 text-gold" />
            <span className="text-[11px] text-gray-400">Avg Confidence</span>
          </div>
          <p className="text-[24px] font-bold text-white">{stats.avgStrength}%</p>
        </div>
      </div>

      {/* Filters */}
      <CollapsibleSection title="Filters" icon={Filter} defaultOpen={false}>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-[13px] text-gray-400 mb-2 block">Source</label>
            <select
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
              className="w-full ios-input"
            >
              {sources.map(source => (
                <option key={source} value={source}>{source === 'all' ? 'All Sources' : source}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[13px] text-gray-400 mb-2 block">Type</label>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="w-full ios-input"
            >
              {types.map(type => (
                <option key={type} value={type}>{type === 'all' ? 'All Types' : type}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[13px] text-gray-400 mb-2 block">Confidence</label>
            <select
              value={selectedStrength}
              onChange={(e) => setSelectedStrength(e.target.value)}
              className="w-full ios-input"
            >
              {strengths.map(strength => (
                <option key={strength.value} value={strength.value}>{strength.label}</option>
              ))}
            </select>
          </div>
        </div>
      </CollapsibleSection>

      {/* Signals List */}
      <div className="space-y-3">
        {filteredSignals.length > 0 ? (
          filteredSignals.map(signal => (
            <SignalCard key={signal.id} signal={signal} />
          ))
        ) : (
          <div className="card-dark p-12 text-center">
            <Clock className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-[17px] text-gray-400">No signals match your filters</p>
            <p className="text-[13px] text-gray-500 mt-2">Try adjusting your filter criteria</p>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default Signals;
