"""
Claude Haiku 4.5 Analysis Service
Lightweight AI-powered price action analysis using Anthropic's Claude
"""
import anthropic
from typing import Dict, List, Optional
import json
from datetime import datetime
import logging
import asyncio

from app.config import settings

logger = logging.getLogger(__name__)


class ClaudeAnalyzer:
    """
    AI analysis service using Claude Haiku 4.5.

    Ultra-lightweight - all compute happens on Anthropic's servers.
    Server only makes API calls and stores results.
    """

    def __init__(self):
        """Initialize Claude client"""
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = "claude-haiku-4-5"  # Claude Haiku 4.5

    async def analyze_price_action(
        self,
        symbol: str,
        price_data: List[Dict],
        indicators: Optional[Dict] = None
    ) -> Dict:
        """
        Analyze price action using Claude Haiku 4.5

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            price_data: List of recent OHLCV candles
            indicators: Optional technical indicators (RSI, MACD, etc.)

        Returns:
            Analysis results with setup identification and confidence scores
        """
        try:
            # Prepare prompt for Claude
            prompt = self._build_analysis_prompt(symbol, price_data, indicators)

            # Call Claude Haiku 4.5
            logger.info(f"🤖 Analyzing {symbol} with Claude Haiku 4.5...")

            message = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0.1,  # Low temp for consistent analysis
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse response
            analysis_text = message.content[0].text
            analysis = self._parse_analysis(analysis_text)

            # Add metadata
            analysis["model"] = self.model
            analysis["timestamp"] = datetime.utcnow().isoformat()
            analysis["token_usage"] = {
                "input": message.usage.input_tokens,
                "output": message.usage.output_tokens
            }

            logger.info(f"✅ Analysis complete for {symbol} (confidence: {analysis.get('confidence', 0):.2f})")

            return analysis

        except Exception as e:
            logger.error(f"❌ Analysis failed for {symbol}: {e}", exc_info=True)
            return {
                "error": str(e),
                "symbol": symbol,
                "timestamp": datetime.utcnow().isoformat()
            }

    def _build_analysis_prompt(
        self,
        symbol: str,
        price_data: List[Dict],
        indicators: Optional[Dict]
    ) -> str:
        """
        Build analysis prompt for Claude

        Format price data and indicators into a clear prompt
        """
        prompt = f"""Analyze the following price action for {symbol} and identify potential trading setups.

**Recent Price Data** (last {len(price_data)} candles):
"""

        # Add price data
        for i, candle in enumerate(price_data[-10:], 1):  # Last 10 candles
            prompt += f"\n{i}. Open: {candle['open']}, High: {candle['high']}, Low: {candle['low']}, Close: {candle['close']}, Volume: {candle.get('volume', 'N/A')}"

        # Add indicators if available
        if indicators:
            prompt += f"\n\n**Technical Indicators**:\n"
            for key, value in indicators.items():
                prompt += f"- {key.upper()}: {value}\n"

        # Analysis instructions
        prompt += """

**Please analyze and provide**:
1. **Trend Direction**: Uptrend, Downtrend, or Sideways
2. **Support Level**: Key support price level
3. **Resistance Level**: Key resistance price level
4. **Setup Type**: breakout, reversal, continuation, or none
5. **Entry Price**: Suggested entry point (if setup exists)
6. **Stop Loss**: Suggested stop loss level
7. **Take Profit**: Suggested take profit target
8. **Confidence Score**: 0.0 to 1.0 (how confident are you in this setup?)
9. **Reasoning**: Brief explanation (2-3 sentences)

**Format your response as JSON**:
```json
{
    "trend": "uptrend|downtrend|sideways",
    "support": 43000.50,
    "resistance": 45000.00,
    "setup_type": "breakout|reversal|continuation|none",
    "entry_price": 43500.00,
    "stop_loss": 42000.00,
    "take_profit": 46000.00,
    "confidence": 0.75,
    "reasoning": "Your brief explanation here"
}
```
"""

        return prompt

    def _parse_analysis(self, analysis_text: str) -> Dict:
        """
        Parse Claude's response into structured data

        Handles both JSON and natural language responses
        """
        try:
            # Try to extract JSON from response
            if "```json" in analysis_text:
                json_start = analysis_text.find("```json") + 7
                json_end = analysis_text.find("```", json_start)
                json_str = analysis_text[json_start:json_end].strip()
            elif "{" in analysis_text and "}" in analysis_text:
                json_start = analysis_text.find("{")
                json_end = analysis_text.rfind("}") + 1
                json_str = analysis_text[json_start:json_end]
            else:
                # No JSON found, return raw text
                return {
                    "raw_analysis": analysis_text,
                    "confidence": 0.0,
                    "setup_type": "none"
                }

            # Parse JSON
            try:
                analysis = json.loads(json_str)
            except json.JSONDecodeError as e:
                # Try to fix common JSON issues
                logger.warning(f"Initial JSON parse failed: {e}, attempting repair...")

                # Fix unescaped newlines in strings
                json_str = json_str.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

                # Try parsing again
                try:
                    analysis = json.loads(json_str)
                    logger.info("✅ JSON repair successful")
                except json.JSONDecodeError as e2:
                    logger.error(f"JSON repair failed: {e2}")
                    # Log the problematic JSON for debugging
                    logger.debug(f"Problematic JSON (first 500 chars): {json_str[:500]}")
                    raise

            # Validate required fields
            required_fields = ["trend", "confidence", "setup_type"]
            for field in required_fields:
                if field not in analysis:
                    logger.warning(f"Missing field in analysis: {field}")
                    analysis[field] = None if field != "confidence" else 0.0

            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse analysis JSON: {e}")
            return {
                "raw_analysis": analysis_text[:1000],  # Truncate to avoid huge logs
                "confidence": 0.0,
                "setup_type": "none",
                "error": "JSON parse error"
            }

    async def analyze_multiple_assets(
        self,
        assets_data: List[Dict]
    ) -> List[Dict]:
        """
        Analyze multiple assets in batch

        Args:
            assets_data: List of dicts with symbol, price_data, indicators

        Returns:
            List of analysis results
        """
        results = []

        for asset in assets_data:
            analysis = await self.analyze_price_action(
                symbol=asset["symbol"],
                price_data=asset["price_data"],
                indicators=asset.get("indicators")
            )

            analysis["symbol"] = asset["symbol"]
            results.append(analysis)

        return results

    async def _fetch_market_data(self, symbol: str, entry_price: float, timeframe: str = "15m") -> Dict:
        """
        Fetch real market data from CCXT for AI analysis

        Returns rich market structure data instead of relying on TradingView indicators
        """
        fetch_start = datetime.utcnow()
        logger.info(f"🔍 [MARKET_DATA] Starting data fetch for {symbol} on {timeframe} timeframe...")
        
        try:
            import ccxt
            import asyncio

            exchange = ccxt.binance({'enableRateLimit': True})
            logger.debug(f"📡 [MARKET_DATA] CCXT Binance exchange initialized for {symbol}")

            # Fetch multiple data sources in parallel
            tasks = []

            # 1. Order book (L2 depth)
            tasks.append(asyncio.to_thread(exchange.fetch_order_book, symbol, limit=20))

            # 2. Recent trades
            tasks.append(asyncio.to_thread(exchange.fetch_trades, symbol, limit=100))

            # 3. Multi-timeframe OHLCV (PRIMARY = webhook timeframe)
            # Map timeframe to fetch appropriate context
            tf_hierarchy = {
                "1m": ("5m", "1m", "15m"),     # lower, primary, higher
                "5m": ("1m", "5m", "15m"),
                "15m": ("5m", "15m", "1h"),
                "1h": ("15m", "1h", "4h"),
                "4h": ("1h", "4h", "1d"),
                "1d": ("4h", "1d", "1w")
            }
            
            lower_tf, primary_tf, higher_tf = tf_hierarchy.get(timeframe.lower(), ("15m", "1h", "4h"))
            
            # Fetch primary timeframe (most data) + higher TF (trend) + lower TF (momentum)
            tasks.append(asyncio.to_thread(exchange.fetch_ohlcv, symbol, primary_tf, limit=100))  # PRIMARY
            tasks.append(asyncio.to_thread(exchange.fetch_ohlcv, symbol, higher_tf, limit=50))    # Trend context
            tasks.append(asyncio.to_thread(exchange.fetch_ohlcv, symbol, lower_tf, limit=150))    # Momentum detail

            # 4. 24h ticker stats
            tasks.append(asyncio.to_thread(exchange.fetch_ticker, symbol))

            # 5. Advanced market data (for perpetuals)
            try:
                # Funding rate (sentiment indicator)
                tasks.append(asyncio.to_thread(exchange.fetch_funding_rate, symbol))
            except:
                tasks.append(None)

            try:
                # Open interest (positioning)
                tasks.append(asyncio.to_thread(exchange.fetch_open_interest, symbol))
            except:
                tasks.append(None)

            try:
                # Liquidations (sentiment extremes)
                tasks.append(asyncio.to_thread(exchange.fetch_my_liquidations, symbol))
            except:
                tasks.append(None)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log each result with detailed status
            order_book = results[0] if not isinstance(results[0], Exception) else None
            if order_book:
                logger.debug(f"✅ [MARKET_DATA] Order book fetched: {len(order_book.get('bids', []))} bids, {len(order_book.get('asks', []))} asks")
            else:
                logger.warning(f"❌ [MARKET_DATA] Order book fetch failed for {symbol}: {results[0]}")
            
            recent_trades = results[1] if not isinstance(results[1], Exception) else None
            if recent_trades:
                logger.debug(f"✅ [MARKET_DATA] Recent trades fetched: {len(recent_trades)} trades")
            else:
                logger.warning(f"❌ [MARKET_DATA] Recent trades fetch failed for {symbol}: {results[1]}")
            
            ohlcv_primary = results[2] if not isinstance(results[2], Exception) else None  # PRIMARY timeframe (webhook's TF)
            if ohlcv_primary:
                logger.debug(f"✅ [MARKET_DATA] Primary TF ({primary_tf}) OHLCV fetched: {len(ohlcv_primary)} candles")
            else:
                logger.warning(f"❌ [MARKET_DATA] Primary TF ({primary_tf}) OHLCV fetch failed for {symbol}: {results[2]}")
            
            ohlcv_higher = results[3] if not isinstance(results[3], Exception) else None   # HIGHER timeframe (trend context)
            if ohlcv_higher:
                logger.debug(f"✅ [MARKET_DATA] Higher TF ({higher_tf}) OHLCV fetched: {len(ohlcv_higher)} candles")
            else:
                logger.warning(f"❌ [MARKET_DATA] Higher TF ({higher_tf}) OHLCV fetch failed for {symbol}: {results[3]}")
            
            ohlcv_lower = results[4] if not isinstance(results[4], Exception) else None    # LOWER timeframe (momentum)
            if ohlcv_lower:
                logger.debug(f"✅ [MARKET_DATA] Lower TF ({lower_tf}) OHLCV fetched: {len(ohlcv_lower)} candles")
            else:
                logger.warning(f"❌ [MARKET_DATA] Lower TF ({lower_tf}) OHLCV fetch failed for {symbol}: {results[4]}")
            
            ticker = results[5] if not isinstance(results[5], Exception) else None
            if ticker:
                logger.debug(f"✅ [MARKET_DATA] 24h ticker fetched: vol=${ticker.get('quoteVolume', 0):.0f}, change={ticker.get('percentage', 0):.2f}%")
            else:
                logger.warning(f"❌ [MARKET_DATA] Ticker fetch failed for {symbol}: {results[5]}")
            
            funding_rate = results[6] if len(results) > 6 and not isinstance(results[6], Exception) else None
            if funding_rate:
                logger.debug(f"✅ [MARKET_DATA] Funding rate fetched: {funding_rate.get('fundingRate', 0)*100:.4f}%")
            else:
                logger.debug(f"ℹ️  [MARKET_DATA] Funding rate not available for {symbol} (may be spot market)")
            
            open_interest = results[7] if len(results) > 7 and not isinstance(results[7], Exception) else None
            if open_interest:
                logger.debug(f"✅ [MARKET_DATA] Open interest fetched")
            else:
                logger.debug(f"ℹ️  [MARKET_DATA] Open interest not available for {symbol}")

            # Analyze order book
            market_data = {
                "order_book_analysis": self._analyze_order_book(order_book, entry_price) if order_book else {},
                "trade_flow_analysis": self._analyze_recent_trades(recent_trades, entry_price) if recent_trades else {},
                "multi_tf_structure": self._analyze_multi_timeframe(
                    ohlcv_primary, ohlcv_higher, ohlcv_lower, entry_price,
                    primary_tf, higher_tf, lower_tf
                ) if ohlcv_primary else {},
                "volume_profile": {
                    "24h_volume": ticker['quoteVolume'] if ticker else 0,
                    "24h_high": ticker['high'] if ticker else 0,
                    "24h_low": ticker['low'] if ticker else 0,
                    "24h_change_pct": ticker['percentage'] if ticker else 0
                } if ticker else {},
                "perpetual_data": {
                    "funding_rate": funding_rate.get('fundingRate') if funding_rate else None,
                    "funding_rate_pct": (funding_rate.get('fundingRate', 0) * 100) if funding_rate and funding_rate.get('fundingRate') else None,
                    "next_funding_time": funding_rate.get('fundingDatetime') if funding_rate else None,
                    "open_interest": open_interest.get('openInterestAmount') or open_interest.get('openInterest') if open_interest and isinstance(open_interest, dict) else (open_interest if open_interest and isinstance(open_interest, (int, float)) else None),
                    "mark_price": funding_rate.get('markPrice') if funding_rate else None,
                    "index_price": funding_rate.get('indexPrice') if funding_rate else None,
                    "premium": ((funding_rate.get('markPrice') - funding_rate.get('indexPrice')) / funding_rate.get('indexPrice') * 100) if funding_rate and funding_rate.get('markPrice') and funding_rate.get('indexPrice') else None
                } if funding_rate or open_interest else None
            }

            fetch_duration = (datetime.utcnow() - fetch_start).total_seconds()
            logger.info(f"✅ [MARKET_DATA] Data fetch completed for {symbol} in {fetch_duration:.2f}s")
            
            return market_data

        except Exception as e:
            fetch_duration = (datetime.utcnow() - fetch_start).total_seconds()
            logger.error(f"❌ [MARKET_DATA] FATAL: Market data fetch failed for {symbol} after {fetch_duration:.2f}s: {e}", exc_info=True)
            return {}

    def _analyze_order_book(self, order_book: Dict, entry_price: float) -> Dict:
        """Analyze order book for support/resistance and liquidity"""
        try:
            bids = order_book.get('bids', [])[:20]
            asks = order_book.get('asks', [])[:20]

            # Calculate bid/ask walls
            bid_liquidity = sum(price * size for price, size in bids)
            ask_liquidity = sum(price * size for price, size in asks)

            # Find largest walls
            largest_bid = max(bids, key=lambda x: x[1]) if bids else [0, 0]
            largest_ask = max(asks, key=lambda x: x[1]) if asks else [0, 0]

            # Distance to walls
            bid_wall_distance = ((entry_price - largest_bid[0]) / entry_price * 100) if largest_bid[0] else 0
            ask_wall_distance = ((largest_ask[0] - entry_price) / entry_price * 100) if largest_ask[0] else 0

            return {
                "bid_ask_ratio": bid_liquidity / ask_liquidity if ask_liquidity > 0 else 0,
                "largest_bid_wall": {"price": largest_bid[0], "size": largest_bid[1], "distance_pct": bid_wall_distance},
                "largest_ask_wall": {"price": largest_ask[0], "size": largest_ask[1], "distance_pct": ask_wall_distance},
                "spread_pct": ((asks[0][0] - bids[0][0]) / entry_price * 100) if bids and asks else 0
            }
        except Exception as e:
            logger.error(f"Order book analysis failed: {e}")
            return {}

    def _analyze_recent_trades(self, trades: List[Dict], entry_price: float) -> Dict:
        """Analyze recent trades for buying/selling pressure"""
        try:
            if not trades:
                return {}

            # Classify trades as buy/sell based on side or taker side
            buys = [t for t in trades if t.get('side') == 'buy' or t.get('takerSide') == 'buy']
            sells = [t for t in trades if t.get('side') == 'sell' or t.get('takerSide') == 'sell']

            buy_volume = sum(t['amount'] * t['price'] for t in buys)
            sell_volume = sum(t['amount'] * t['price'] for t in sells)

            # Calculate aggression (large trades)
            large_trades = [t for t in trades if t['amount'] * t['price'] > 10000]  # $10k+ trades

            return {
                "buy_sell_ratio": buy_volume / sell_volume if sell_volume > 0 else 0,
                "buy_volume_usd": buy_volume,
                "sell_volume_usd": sell_volume,
                "large_trade_count": len(large_trades),
                "net_flow": "buying" if buy_volume > sell_volume else "selling"
            }
        except Exception as e:
            logger.error(f"Trade flow analysis failed: {e}")
            return {}

    def _analyze_multi_timeframe(self, ohlcv_primary: List, ohlcv_higher: List, ohlcv_lower: List, entry_price: float, primary_tf: str, higher_tf: str, lower_tf: str) -> Dict:
        """Analyze price structure across multiple timeframes (dynamic based on webhook timeframe)"""
        try:
            analysis = {}

            # Analyze PRIMARY timeframe (webhook's timeframe - MOST IMPORTANT)
            if ohlcv_primary and len(ohlcv_primary) >= 10:
                recent_primary = ohlcv_primary[-20:]
                closes = [c[4] for c in recent_primary]
                analysis[f'{primary_tf}_trend'] = "uptrend" if closes[-1] > closes[0] else "downtrend"
                analysis[f'{primary_tf}_momentum'] = ((closes[-1] - closes[0]) / closes[0] * 100)
                analysis['primary_timeframe'] = primary_tf  # Label for AI prompt

            # Analyze HIGHER timeframe (trend context)
            if ohlcv_higher and len(ohlcv_higher) >= 10:
                recent_higher = ohlcv_higher[-15:]
                closes = [c[4] for c in recent_higher]
                analysis[f'{higher_tf}_trend'] = "uptrend" if closes[-1] > closes[0] else "downtrend"
                analysis[f'{higher_tf}_momentum'] = ((closes[-1] - closes[0]) / closes[0] * 100)
                analysis['higher_timeframe'] = higher_tf

            # Analyze LOWER timeframe (momentum detail)
            if ohlcv_lower and len(ohlcv_lower) >= 24:
                recent_lower = ohlcv_lower[-24:]
                closes = [c[4] for c in recent_lower]
                volumes = [c[5] for c in recent_lower]
                analysis[f'{lower_tf}_trend'] = "uptrend" if closes[-1] > closes[0] else "downtrend"
                analysis[f'{lower_tf}_volume_trend'] = "increasing" if volumes[-1] > sum(volumes[:12])/12 else "decreasing"
                analysis['lower_timeframe'] = lower_tf

            return analysis
        except Exception as e:
            logger.error(f"Multi-timeframe analysis failed: {e}")
            return {}

    async def _fetch_tradingview_data(self, symbol: str, timeframe: str) -> Dict:
        """
        Fetch TradingView technical indicators via MCP
        
        Returns:
            Technical analysis data including:
            - Bollinger Band rating (-3 to +3)
            - RSI, MACD, ADX values
            - Consecutive candle patterns
            - Market ranking (top gainer/loser)
        """
        try:
            from mcp.client.session import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client
            from mcp import types
            import json

            # Convert symbol format (BTCUSDT.P -> BTCUSDT, remove perpetual suffix)
            clean_symbol = symbol.replace(".P", "").replace("USDT", "USDT")

            # Map timeframe to TradingView format
            timeframe_map = {
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "1h": "1h",
                "4h": "4h",
                "1d": "1d",
                "1D": "1d"
            }
            tv_timeframe = timeframe_map.get(timeframe.lower(), "15m")

            logger.info(f"📈 Fetching TradingView TA for {clean_symbol} ({tv_timeframe}) via MCP...")

            # Connect to TradingView MCP server
            server_params = StdioServerParameters(
                command="uv",
                args=[
                    "tool", "run",
                    "--from", "git+https://github.com/atilaahmettaner/tradingview-mcp.git",
                    "tradingview-mcp"
                ]
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize connection
                    await session.initialize()

                    # Call coin_analysis tool
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "coin_analysis",
                            arguments={
                                "symbol": clean_symbol,
                                "exchange": "BINANCE",
                                "timeframe": tv_timeframe
                            }
                        ),
                        timeout=10.0
                    )

                    # Extract data from result
                    if result.structuredContent:
                        tv_data = result.structuredContent
                    elif result.content and len(result.content) > 0:
                        # Fallback to unstructured content
                        content = result.content[0]
                        if isinstance(content, types.TextContent):
                            tv_data = json.loads(content.text)
                        else:
                            raise ValueError("Unexpected content type from MCP")
                    else:
                        raise ValueError("No data returned from TradingView MCP")

                    # Extract key indicators (adapt based on actual MCP response structure)
                    indicators = tv_data.get("indicators", {})

                    logger.info(f"✅ Got TradingView data for {clean_symbol}")

                    return {
                        "bollinger_rating": tv_data.get("bollinger_rating"),
                        "bollinger_width": tv_data.get("bollinger_width"),
                        "rsi": indicators.get("RSI"),
                        "macd": indicators.get("MACD"),
                        "macd_signal": indicators.get("MACD_Signal"),
                        "adx": indicators.get("ADX"),
                        "stochastic_k": indicators.get("Stoch_K"),
                        "stochastic_d": indicators.get("Stoch_D"),
                        "sma20": indicators.get("SMA20"),
                        "ema50": indicators.get("EMA50"),
                        "ema200": indicators.get("EMA200"),
                        "consecutive_candles": tv_data.get("consecutive_candles"),
                        "pattern": tv_data.get("pattern"),
                        "trend": tv_data.get("trend"),
                        "volume_analysis": tv_data.get("volume"),
                        "price_vs_bb": tv_data.get("price_position")
                    }

        except asyncio.TimeoutError:
            logger.error("TradingView MCP timeout (10s)")
            logger.info("Trying TradingView-API fallback...")
            return await self._fetch_tradingview_fallback(symbol, timeframe)
        except Exception as e:
            logger.error(f"TradingView MCP failed: {e}")
            logger.info("Trying TradingView-API fallback...")
            return await self._fetch_tradingview_fallback(symbol, timeframe)

    async def _fetch_tradingview_fallback(self, symbol: str, timeframe: str) -> Dict:
        """
        Fallback: Calculate TA indicators from OHLCV data using pandas-ta
        
        This provides redundancy so we always get TA data even if TradingView fails
        """
        try:
            import pandas as pd
            import pandas_ta as ta
            import ccxt
            import asyncio
            
            logger.info(f"📊 Fallback: Calculating TA indicators from OHLCV for {symbol}...")
            
            # Map timeframe
            timeframe_map = {
                "5m": "5m",
                "15m": "15m",
                "1h": "1h",
                "4h": "4h",
                "1d": "1d",
                "1D": "1d"
            }
            tf = timeframe_map.get(timeframe.lower(), "15m")
            
            # Fetch OHLCV data via CCXT
            exchange = ccxt.binance({'enableRateLimit': True})
            ohlcv = await asyncio.to_thread(exchange.fetch_ohlcv, symbol, tf, limit=200)
            
            if not ohlcv or len(ohlcv) < 50:
                logger.error("Insufficient OHLCV data for indicator calculation")
                return {}
            
            # Convert to pandas DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Calculate indicators
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.adx(length=14, append=True)
            df.ta.ema(length=50, append=True)
            df.ta.ema(length=200, append=True)
            df.ta.sma(length=20, append=True)
            
            latest = df.iloc[-1]
            price = latest['close']
            
            # Calculate BB rating
            bb_upper = latest.get('BBU_20_2.0', 0)
            bb_lower = latest.get('BBL_20_2.0', 0)
            bb_middle = latest.get('BBM_20_2.0', 0)
            
            bbRating = 0
            if bb_middle > 0:
                bb_width = ((bb_upper - bb_lower) / bb_middle * 100)
                if price > bb_upper: bbRating = 3
                elif price > bb_middle:
                    bbRating = min(2, int((price - bb_middle) / (bb_upper - bb_middle) * 2))
                elif price < bb_lower: bbRating = -3
                elif price < bb_middle:
                    bbRating = max(-2, -int((bb_middle - price) / (bb_middle - bb_lower) * 2))
            else:
                bb_width = None
            
            # Calculate consecutive candles
            consecutiveBullish = 0
            consecutiveBearish = 0
            for i in range(len(df) - 1, max(0, len(df) - 11), -1):
                if df.iloc[i]['close'] > df.iloc[i]['open']:
                    if consecutiveBearish == 0: consecutiveBullish += 1
                    else: break
                elif df.iloc[i]['close'] < df.iloc[i]['open']:
                    if consecutiveBullish == 0: consecutiveBearish += 1
                    else: break
                else: break
            
            fallback_data = {
                "bollinger_rating": bbRating,
                "bollinger_width": bb_width,
                "rsi": latest.get('RSI_14'),
                "macd": latest.get('MACD_12_26_9'),
                "macd_signal": latest.get('MACDs_12_26_9'),
                "adx": latest.get('ADX_14'),
                "ema50": latest.get('EMA_50'),
                "ema200": latest.get('EMA_200'),
                "sma20": latest.get('SMA_20'),
                "consecutive_candles": consecutiveBullish if consecutiveBullish > 0 else -consecutiveBearish,
                "pattern": "bullish_momentum" if consecutiveBullish >= 3 else "bearish_momentum" if consecutiveBearish >= 3 else "neutral",
                "trend": "uptrend" if price > latest.get('EMA_50', 0) else "downtrend",
                "price_vs_bb": "above_middle" if bbRating > 0 else "below_middle" if bbRating < 0 else "at_middle",
                "source": "pandas-ta-fallback"
            }
            
            logger.info(f"✅ Fallback TA calculation success (RSI: {fallback_data.get('rsi', 'N/A'):.2f})")
            return fallback_data
            
        except Exception as e:
            logger.error(f"TA fallback calculation failed: {e}")
            return {}

    async def evaluate_setup_quality(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        timeframe: str,
        indicators: Optional[Dict] = None
    ) -> Dict:
        """
        Evaluate setup quality BEFORE taking the trade (Pre-Entry Analysis)

        This is Phase 1: Data collection only - doesn't block trades

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            direction: "LONG" or "SHORT"
            entry_price: Entry price
            timeframe: Timeframe (e.g., "15m", "1h")
            indicators: Technical indicators from TradingView (optional, not primary source)

        Returns:
            AI evaluation with quality score, confidence, red flags
        """
        try:
            # CRITICAL VALIDATION: Reject invalid entry prices immediately
            if entry_price is None or entry_price <= 0:
                logger.error(f"❌ INVALID ENTRY PRICE: {entry_price} for {symbol} {direction}")
                return {
                    "error": f"Invalid entry_price: {entry_price}",
                    "quality_score": 0.0,
                    "confidence": 0.0,
                    "narrative": f"CRITICAL ERROR: Entry price ${entry_price} is invalid. Cannot analyze setup with zero or negative price.",
                    "reasoning": "SKIP - Invalid data (entry_price must be > 0)",
                    "recommended_action": "skip",
                    "key_confluences": [],
                    "key_divergences": ["Invalid entry_price data"],
                    "setup_type": "invalid_data",
                    "timestamp": datetime.utcnow().isoformat()
                }

            # Fetch real market data from CCXT (using webhook's timeframe as PRIMARY)
            logger.info(f"📊 Fetching market data for {symbol} on {timeframe} timeframe...")
            market_data = await self._fetch_market_data(symbol, entry_price, timeframe)
            
            # Log data completeness for diagnostics
            missing_data = []
            if not market_data.get('order_book_analysis'):
                missing_data.append("order book data")
            if not market_data.get('trade_flow_analysis'):
                missing_data.append("trade flow data")
            if not market_data.get('multi_tf_structure'):
                missing_data.append("technical analysis")
            if not market_data.get('perpetual_data'):
                missing_data.append("perpetual data (funding rates, OI)")
            
            if missing_data:
                logger.warning(f"⚠️  Missing market data for {symbol}: {', '.join(missing_data)}")
            
            # Fetch TradingView technical indicators
            logger.info(f"📈 Fetching TradingView TA for {symbol}...")
            tv_data = await self._fetch_tradingview_data(symbol, timeframe)
            
            if not tv_data or len(tv_data) == 0:
                logger.warning(f"⚠️  No TradingView data received for {symbol}")

            # Determine trading style context based on timeframe
            if timeframe in ['1m', '5m']:
                trading_style = "SCALPING"
                tf_context = """**TRADING STYLE: SCALPING (1m-5m)**

You are analyzing a SCALP trade - this is about capturing quick momentum moves, NOT following long-term trends.

**Key Analysis Priorities for Scalping:**
1. **IMMEDIATE momentum** (5m/15m trends) - Is there buying/selling pressure RIGHT NOW?
2. **Order flow** - Are market orders hitting bids/asks aggressively? This shows conviction.
3. **Microstructure** - Recent candle patterns, consecutive moves, BB squeezes on SHORT timeframes
4. **Volume spikes** - Sudden interest in the last few candles = scalp opportunity
5. **Funding rate** - Extreme readings (>0.03% or <-0.03%) can trigger quick reversals for scalps

**What DOESN'T matter much for scalping:**
- 1h/4h/daily trends (too slow for scalps)
- Long-term fundamentals
- Weekly support/resistance zones

**Ideal Scalp Setup (8-10/10):**
- 5m/15m momentum strongly aligned with direction
- Order flow showing aggressive market orders
- Volume spike in last 1-5 candles
- BB squeeze or consecutive candles showing clear microstructure momentum
- Funding NOT extreme (no imminent reversal pressure)

**Acceptable Scalp (6-7/10):**
- Clear momentum on signal timeframe even if 1h is sideways/opposite
- Decent volume, clear order flow direction

**Weak Scalp (3-5/10):**
- No clear momentum on 5m/15m
- Flat volume, mixed order flow
- Funding extreme (risk of quick reversal)"""
            elif timeframe in ['15m', '30m']:
                trading_style = "INTRADAY SWING"
                tf_context = """**TRADING STYLE: INTRADAY SWING (15m-30m)**

You are analyzing an INTRADAY trade - medium-term position (hours), looking to capture larger swings within the day.

**Key Analysis Priorities:**
1. **15m/1h alignment** - Both timeframes should generally agree on direction
2. **Market structure** - Is the 1h trend supportive or at least not strongly opposing?
3. **Funding + OI** - Positioning data becomes more relevant for multi-hour holds
4. **Technical indicators** - RSI, MACD, EMAs on 15m/1h matter more here
5. **Volume profile** - Sustained volume over multiple candles (not just spike)

**What matters moderately:**
- 4h trend (context, but not dealbreaker if 1h is strong)
- Key support/resistance zones

**What matters less:**
- 1m/5m micro moves (noise for intraday)
- Tick-by-tick order flow

**Ideal Intraday Setup (8-10/10):**
- 15m and 1h trends aligned
- Funding/OI showing healthy positioning (no extreme crowding)
- Technical confluence (RSI trending, MACD crossover, price above key EMAs)
- Volume sustained over last hour, not just recent spike

**Acceptable (6-7/10):**
- 15m strong even if 1h is consolidating
- Decent technicals and positioning

**Weak (3-5/10):**
- 15m and 1h opposing
- Extreme funding or falling OI during intended direction"""
            else:  # 1h, 4h, 1d
                trading_style = "SWING/POSITION"
                tf_context = """**TRADING STYLE: SWING/POSITION TRADE (1h+)**

You are analyzing a SWING trade - this is about riding major trend moves over days/weeks, NOT quick scalps.

**Key Analysis Priorities:**
1. **Multi-timeframe trend alignment** (1h, 4h, daily) - The BIG picture matters most
2. **Macro market structure** - Are we in an uptrend, downtrend, or range?
3. **Positioning extremes** - Funding rates >0.05% or <-0.05%, OI at extremes
4. **Major support/resistance** - Weekly/daily levels that could halt the move
5. **Long-term indicators** - 50 EMA, 200 EMA, weekly RSI, higher TF MACD

**What DOESN'T matter for swings:**
- 1m/5m/15m microstructure (too granular for days-long holds)
- Single candle patterns on low timeframes
- Minute-to-minute order flow

**Ideal Swing Setup (8-10/10):**
- 1h, 4h, daily all aligned in same direction
- Price above/below major EMAs (50/200) in direction of trade
- Funding/OI healthy (not extreme exhaustion)
- Coming off major support/resistance with conviction

**Acceptable Swing (6-7/10):**
- 1h and 4h aligned even if daily mixed
- Some technical confluence

**Weak Swing (3-5/10):**
- Higher TFs opposing signal timeframe
- Extreme funding (>0.08% = very crowded positioning)
- Major resistance ahead for longs / major support ahead for shorts"""

            prompt = f"""You are an expert price action and order flow trader. Analyze this trade setup using REAL MARKET DATA.

**Setup:**
- Symbol: {symbol}
- Direction: {direction}
- Entry: ${entry_price:,.2f}
- Timeframe: {timeframe}

{tf_context}

**REAL MARKET DATA (from CCXT):**
{json.dumps(market_data, indent=2)}

**TRADINGVIEW TECHNICAL ANALYSIS:**
{json.dumps(tv_data, indent=2)}

**Your Task:**
You are analyzing a {direction} entry signal for {symbol} on **{timeframe} ({trading_style})**. Your job is to construct a HOLISTIC NARRATIVE from all available data that's RELEVANT FOR THIS TRADING STYLE.

**CRITICAL: Everything Is Interconnected**

Do NOT treat indicators as a checklist. Do NOT weight one signal over another. EVERYTHING weaves together into a complete picture.

**How to Build Your Narrative:**

Think like a detective building a case. Each piece of evidence (order flow, funding, TA, volume) adds to the story:

**The Market Structure Story:**
- **CRITICAL**: The PRIMARY timeframe is **{timeframe}** - this is what TradingView signaled on. Analyze what matters for {trading_style}.
- What is the market doing across the RELEVANT timeframes for this trade style? (see trading style context above)
- Where is price relative to structure? (Bollinger bands, EMAs, key levels)
- Is the market in expansion (trending) or contraction (ranging)? (BB width, ADX, volume)

**The Positioning Story:**
- Who is in control? Smart money or retail? (buy/sell ratio, large trades, order book walls)
- Are NEW positions entering or OLD positions covering? (OI rising vs falling + price direction)
- Is the crowd too one-sided? (funding rate extremes, OI + funding combined)

**The Momentum Story:**
- Is momentum building or fading? (consecutive candles, MACD, volume trend)
- Are we at exhaustion or beginning of move? (RSI, BB rating, consecutive candles)
- Do indicators confirm or diverge from price? (RSI divergence, MACD vs price)

**The Confluence Question:**
How do ALL these stories align? The magic isn't in any ONE indicator being bullish/bearish - it's in the PATTERN that emerges when you look at EVERYTHING together.

**Example: A LONG Signal Analysis (Holistic Thinking)**

Instead of:
"✅ 1h uptrend, ✅ RSI 58, ✅ OI rising, ✅ BB squeeze → Score: 8/10"

Think:
"Looking at the complete picture: Price has been consolidating in a tight BB squeeze (width: 8) while the PRIMARY timeframe ({timeframe}) and higher TF both show higher lows forming - suggesting accumulation. The order book shows bid/ask ratio of 3.2 with a large wall 0.3% below entry (support), and recent trade flow is heavily buy-sided (buy/sell: 3.2). 

Now here's where it gets interesting: OI is RISING as price climbs, meaning these are NEW longs entering (not short covering). Funding is neutral at 0.005% so there's no crowd positioning extreme. 

The TA paints the same picture: RSI at 58 (healthy uptrend zone, not overheated), MACD just crossed bullish, 4 consecutive bullish candles show momentum building, and price is above EMA50/EMA200 (trend structure intact). ADX at 28 confirms this is a real trend, not chop.

This is a CONFLUENCE SETUP: Structure (BB squeeze breakout) + Positioning (smart money accumulating, new longs) + Momentum (building, not exhausted) + Timeframe alignment (PRIMARY {timeframe} + higher/lower TFs) all tell the SAME story. The entry is at a support level with smart money backing it.

Quality: 9.5/10 - This is an A+ setup where every piece of the puzzle fits together."

**Another Example: A SHORT Signal That Looks Good But ISN'T (Holistic Red Flag)**

Instead of:
"❌ Funding -0.03% (extreme), ❌ OI falling → Skip"

Think:
"At first glance, this SHORT looks promising: PRIMARY timeframe ({timeframe}) downtrend, price below EMAs, RSI at 40 (bearish territory). But when I look at the COMPLETE picture, something's off.

Funding rate is -0.03% (extreme short crowding) AND open interest is FALLING as price drops. This isn't new shorts entering - this is longs being liquidated and shorts covering old positions. The order flow confirms it: buy/sell ratio is 1.8 (buyers stepping in), and there's a large bid wall 0.5% below.

The TA shows exhaustion: 6 consecutive bearish candles (overdone), BB rating at -3 (price below lower band, oversold), RSI showing bullish divergence (price making new lows but RSI not confirming).

This is a SHORT SQUEEZE EXHAUSTION setup, not a new downtrend. The crowd is already massively short (funding), positions are closing (OI falling), buyers are accumulating (order flow), and TA screams reversal (divergence, oversold).

Quality: 2/10 - Everything points to the move being OVER, not starting. Taking this SHORT is fading into a squeeze."

**YOUR ANALYSIS MUST:**
1. Build a narrative that connects ALL the data points into a cohesive story
2. Explain WHY certain combinations matter (e.g., OI rising + price up = NEW longs vs OI falling + price up = covering)
3. Look for CONFLUENCE (when multiple independent data sources tell the same story)
4. Identify DIVERGENCES (when something doesn't fit the narrative - these are red flags)
5. Give context to every data point - nothing exists in isolation

** (Learn from this - REMEMBER: The user's strategies ARE PROFITABLE, so be generous with scoring):**

**Example 1: EXCELLENT SETUP (9-10/10) - Multiple Confluences**
- **CCXT**: 1h uptrend ✅, 15m uptrend ✅, volume increasing ✅
- **CCXT**: Funding: 0.005% (neutral) ✅, OI rising ✅ = NEW positions entering
- **CCXT**: Buy/sell ratio: 3.2 ✅, Bid/ask: 4.1 ✅ = Smart money present
- **TradingView**: BB Width: 8 (squeeze) ✅, RSI: 58 ✅, MACD > Signal ✅
- **TradingView**: 4 consecutive bullish candles ✅, Price > EMA50 > EMA200 ✅
**Verdict: 9.5/10 - EXCELLENT (Everything aligns perfectly)**

**Example 2: GOOD SETUP (7-8/10) - Main Trend Aligned**
- 1h uptrend ✅, 15m consolidation (acceptable)
- Funding: 0.015% (normal range, not extreme)
- OI rising slowly ✅, buy pressure present
- RSI: 62 (trending, healthy), MACD positive ✅
**Verdict: 7.5/10 - GOOD (Trend is your friend, solid entry)**

**Example 3: ACCEPTABLE SETUP (5-6/10) - One Strong Signal**
- 1h sideways BUT 15m momentum strong ✅
- Funding neutral ✅, volume confirming move ✅
- Price breaking key level with conviction
**Verdict: 6/10 - ACCEPTABLE (Momentum trade with confirmation)**

**Example 4: CAUTION SETUP (3-4/10) - Counter-Trend**
- 1h downtrend ✅, BUT funding: -0.04% (extreme shorts) ⚠️
- OI falling + price dropping = Liquidation cascade, not new shorts
**Verdict: 3/10 - CAUTION (Potential reversal zone, risky)**

**SCORING PHILOSOPHY: Be generous. If trend + volume align, that's 6/10 minimum. Reserve low scores (1-3) for EXTREME situations only (funding > 0.05%, all TFs opposing, liquidation cascades).**

**RESPOND IN VALID JSON ONLY - NO ADDITIONAL TEXT:**

CRITICAL: Your response must be ONLY valid JSON. No markdown, no explanations, no backticks. Ensure all strings are properly escaped - use only double quotes, escape any quotes inside strings with backslash.

{{
    "quality_score": 7.5,
    "confidence": 0.75,
    "setup_type": "confluence_breakout",
    "narrative": "Your complete holistic analysis. Tell the story of what ALL the data is saying together. 3-5 sentences minimum. Connect order flow + positioning + momentum + structure into ONE cohesive picture. Keep all text on a single line.",
    "key_confluences": ["List 2-4 things that align and tell the same story"],
    "key_divergences": ["List any data points that don't fit the narrative - these are warning signs"],
    "reasoning": "Why is this quality score justified based on the COMPLETE PICTURE? Not a checklist, but an explanation of how everything weaves together. Keep all text on a single line.",
    "recommended_action": "take",
    "trend": "bullish"
}}

Valid setup_type values: "confluence_breakout", "squeeze_exhaustion", "trend_continuation", "divergence_reversal", "weak_structure", "none"
Valid recommended_action values: "take", "skip", "wait_for_confirmation"
Valid trend values: "bullish", "bearish", "sideways", "unknown"
"""

            logger.info(f"🤖 Evaluating setup quality for {symbol} {direction}...")

            # Wrap Claude API call with timeout to prevent blocking webhook handler
            try:
                message = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.messages.create,
                        model=self.model,
                        max_tokens=1200,
                        temperature=0.2,
                        messages=[{"role": "user", "content": prompt}]
                    ),
                    timeout=35.0  # 35 second timeout (market data fetch can take 20-25s)
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ AI analysis timeout for {symbol} after 35s (likely CCXT data fetch taking too long)")
                return {
                    "error": "AI timeout",
                    "quality_score": 5.0,  # Neutral score
                    "confidence": 0.0,
                    "reasoning": "AI analysis timed out after 35s - market data fetch took too long",
                    "recommended_action": "take",  # Default to taking trade if AI unavailable
                    "narrative": "AI analysis timed out. Market data fetch from CCXT exceeded 35 second limit. Trade will proceed with neutral 5/10 score.",
                    "key_confluences": [],
                    "key_divergences": ["AI timeout"],
                    "setup_type": "none",
                    "timestamp": datetime.utcnow().isoformat()
                }

            analysis_text = message.content[0].text
            analysis = self._parse_analysis(analysis_text)

            # Validate and clamp AI output ranges
            if 'quality_score' in analysis:
                analysis['quality_score'] = max(0.0, min(10.0, float(analysis.get('quality_score', 5.0))))
            else:
                analysis['quality_score'] = 5.0  # Neutral default

            if 'confidence' in analysis:
                analysis['confidence'] = max(0.0, min(1.0, float(analysis.get('confidence', 0.0))))
            else:
                analysis['confidence'] = 0.0  # No confidence default

            # Validate setup_type is one of expected values
            valid_types = ['confluence_breakout', 'squeeze_exhaustion', 'trend_continuation',
                           'divergence_reversal', 'weak_structure', 'invalid_data', 'none']
            if analysis.get('setup_type') not in valid_types:
                logger.warning(f"Invalid setup_type: {analysis.get('setup_type')}, defaulting to 'none'")
                analysis['setup_type'] = 'none'

            # Validate recommended_action
            valid_actions = ['take', 'skip', 'wait_for_confirmation']
            if analysis.get('recommended_action') not in valid_actions:
                logger.warning(f"Invalid recommended_action: {analysis.get('recommended_action')}, defaulting to 'skip'")
                analysis['recommended_action'] = 'skip'

            # Add metadata
            analysis["model"] = self.model
            analysis["timestamp"] = datetime.utcnow().isoformat()
            analysis["token_usage"] = {
                "input": message.usage.input_tokens,
                "output": message.usage.output_tokens
            }

            logger.info(
                f"✅ Setup evaluation complete: Quality={analysis.get('quality_score', 0)}/10, "
                f"Confidence={analysis.get('confidence', 0):.2f}"
            )

            return analysis

        except Exception as e:
            logger.error(f"❌ Setup evaluation failed for {symbol}: {e}", exc_info=True)
            return {
                "error": str(e),
                "quality_score": 5.0,  # Neutral score on error
                "confidence": 0.0,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def analyze_trade_outcome(
        self,
        trade: "TradeSetup",
        final_outcome: str,
        final_pnl: float
    ) -> Dict:
        """
        Analyze completed trade to extract learnings (Post-Trade Analysis)

        This builds a knowledge base of WHAT WORKS and WHEN

        Args:
            trade: Completed trade object
            final_outcome: "tp1", "tp2", "tp3", "sl", "timeout"
            final_pnl: Final PnL percentage

        Returns:
            AI insights: patterns, lessons, market regime
        """
        try:
            prompt = f"""Analyze this completed trade to extract key learnings.

**Trade Summary:**
- Symbol: {trade.symbol} {trade.direction}
- Entry: ${trade.entry_price}
- Outcome: {final_outcome} ({final_pnl:+.2f}%)
- Duration: {((trade.completed_at - trade.entry_timestamp).total_seconds() / 60):.0f} minutes
- Max Profit: {trade.max_profit_pct}%
- Max Drawdown: {trade.max_drawdown_pct}%
- TP Hits: TP1={trade.tp1_hit}, TP2={trade.tp2_hit}, TP3={trade.tp3_hit}

**AI Pre-Entry Assessment (if available):**
- Quality Score: {trade.ai_quality_score}/10
- Confidence: {trade.ai_confidence}
- Red Flags: {trade.ai_red_flags}

**Analysis Questions:**
1. WHY did this trade {'win' if final_pnl > 0 else 'lose'}?
2. Was the AI pre-entry assessment correct?
3. What market conditions led to this outcome?
4. What pattern/structure was this? (breakout, fakeout, reversal, continuation)
5. What can we learn for future {trade.symbol} {trade.direction} trades?

**Respond in JSON:**
{{
    "analysis": "Detailed 3-4 sentence analysis of why this outcome occurred",
    "pattern": "strong_breakout",
    "market_regime": "trending",
    "ai_assessment_accuracy": "correct",
    "lessons": [
        "Lesson 1: Specific actionable insight",
        "Lesson 2: What to look for next time"
    ]
}}
"""

            logger.info(f"🤖 Analyzing completed trade {trade.id} ({trade.symbol} {trade.direction})...")

            message = self.client.messages.create(
                model=self.model,
                max_tokens=600,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )

            analysis_text = message.content[0].text
            analysis = self._parse_analysis(analysis_text)

            # Add metadata
            analysis["model"] = self.model
            analysis["timestamp"] = datetime.utcnow().isoformat()
            analysis["token_usage"] = {
                "input": message.usage.input_tokens,
                "output": message.usage.output_tokens
            }

            logger.info(
                f"✅ Post-trade analysis complete: Pattern={analysis.get('pattern')}, "
                f"Regime={analysis.get('market_regime')}"
            )

            return analysis

        except Exception as e:
            logger.error(f"❌ Post-trade analysis failed for trade {trade.id}: {e}", exc_info=True)
            return {
                "error": str(e),
                "analysis": "Analysis failed",
                "pattern": "unknown",
                "market_regime": "unknown",
                "timestamp": datetime.utcnow().isoformat()
            }


# Global analyzer instance
_analyzer = None

def get_analyzer() -> ClaudeAnalyzer:
    """Get or create global analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = ClaudeAnalyzer()
    return _analyzer
