#!/usr/bin/env node
/**
 * TradingView Fallback - Get real-time indicator values
 * Called when TradingView MCP fails
 *
 * Usage: node tradingview_fallback.js BINANCE:BTCUSDT 15
 */

const TradingView = require('@mathieuc/tradingview');

const symbol = process.argv[2] || 'BINANCE:BTCUSDT';
const timeframe = process.argv[3] || '15';

async function getIndicators() {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      try { client.end(); } catch (e) {}
      reject(new Error('Timeout after 12 seconds'));
    }, 12000);

    const client = new TradingView.Client();
    const chart = new client.Session.Chart();

    chart.setMarket(symbol, {
      timeframe: timeframe,
      range: 100,
    });

    const RSI = new chart.Study('RSI');
    const MACD = new chart.Study('MACD');
    const BB = new chart.Study('BB');
    const ADX = new chart.Study('ADX');
    const EMA50 = new chart.Study('EMA');
    EMA50.setOption('length', 50);
    const EMA200 = new chart.Study('EMA');
    EMA200.setOption('length', 200);
    const SMA20 = new chart.Study('SMA');
    SMA20.setOption('length', 20);

    chart.onError((...err) => {
      clearTimeout(timeout);
      try { client.end(); } catch (e) {}
      reject(new Error(`Chart error: ${err.join(' ')}`));
    });

    let updateCount = 0;
    chart.onUpdate(() => {
      updateCount++;

      // Wait for at least 2 updates to ensure data is loaded
      if (updateCount < 2) return;

      try {
        const periods = chart.periods;
        if (!periods || periods.length === 0) return;

        const latest = periods[periods.length - 1];

        // Get indicator values
        const rsiPeriods = RSI.periods;
        const macdPeriods = MACD.periods;
        const bbPeriods = BB.periods;
        const adxPeriods = ADX.periods;
        const ema50Periods = EMA50.periods;
        const ema200Periods = EMA200.periods;
        const sma20Periods = SMA20.periods;

        // Calculate BB rating
        let bbRating = 0;
        const price = latest.close;
        if (bbPeriods && bbPeriods.length > 0) {
          const bbLast = bbPeriods[bbPeriods.length - 1];
          const bbUpper = bbLast.upper || 0;
          const bbLower = bbLast.lower || 0;
          const bbMiddle = bbLast.median || 0;
          const bbWidth = bbMiddle > 0 ? ((bbUpper - bbLower) / bbMiddle * 100) : 0;

          if (price > bbUpper) bbRating = 3;
          else if (price > bbMiddle && price < bbUpper) {
            bbRating = Math.round((price - bbMiddle) / (bbUpper - bbMiddle) * 2);
          } else if (price < bbLower) bbRating = -3;
          else if (price < bbMiddle && price > bbLower) {
            bbRating = -Math.round((bbMiddle - price) / (bbMiddle - bbLower) * 2);
          }
        }

        // Calculate consecutive candles
        let consecutiveBullish = 0;
        let consecutiveBearish = 0;
        for (let i = periods.length - 1; i >= Math.max(0, periods.length - 10); i--) {
          if (periods[i].close > periods[i].open) {
            if (consecutiveBearish === 0) consecutiveBullish++;
            else break;
          } else if (periods[i].close < periods[i].open) {
            if (consecutiveBullish === 0) consecutiveBearish++;
            else break;
          } else break;
        }

        const output = {
          bollinger_rating: bbRating,
          bollinger_width: bbPeriods.length > 0 ?
            ((bbPeriods[bbPeriods.length - 1].upper - bbPeriods[bbPeriods.length - 1].lower) /
             bbPeriods[bbPeriods.length - 1].median * 100) : null,
          rsi: rsiPeriods && rsiPeriods.length > 0 ? rsiPeriods[rsiPeriods.length - 1].plot_0 : null,
          macd: macdPeriods && macdPeriods.length > 0 ? macdPeriods[macdPeriods.length - 1].plot_0 : null,
          macd_signal: macdPeriods && macdPeriods.length > 0 ? macdPeriods[macdPeriods.length - 1].plot_1 : null,
          adx: adxPeriods && adxPeriods.length > 0 ? adxPeriods[adxPeriods.length - 1].plot_0 : null,
          ema50: ema50Periods && ema50Periods.length > 0 ? ema50Periods[ema50Periods.length - 1].plot_0 : null,
          ema200: ema200Periods && ema200Periods.length > 0 ? ema200Periods[ema200Periods.length - 1].plot_0 : null,
          sma20: sma20Periods && sma20Periods.length > 0 ? sma20Periods[sma20Periods.length - 1].plot_0 : null,
          consecutive_candles: consecutiveBullish > 0 ? consecutiveBullish : -consecutiveBearish,
          pattern: consecutiveBullish >= 3 ? 'bullish_momentum' : consecutiveBearish >= 3 ? 'bearish_momentum' : 'neutral',
          trend: ema50Periods && ema50Periods.length > 0 && price > ema50Periods[ema50Periods.length - 1].plot_0 ? 'uptrend' : 'downtrend',
          price_vs_bb: bbRating > 0 ? 'above_middle' : bbRating < 0 ? 'below_middle' : 'at_middle',
          source: 'tradingview-api-fallback'
        };

        clearTimeout(timeout);
        console.log(JSON.stringify(output));
        try { client.end(); } catch (e) {}
        resolve();
      } catch (error) {
        clearTimeout(timeout);
        try { client.end(); } catch (e) {}
        reject(error);
      }
    });
  });
}

getIndicators()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(JSON.stringify({ error: error.message }));
    process.exit(1);
  });
