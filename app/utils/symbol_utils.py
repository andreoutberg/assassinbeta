"""
Symbol Normalization Utilities

Converts between different symbol formats across data sources.

## EXCHANGE SYMBOL FORMATS REFERENCE ##

### TradingView (webhook source)
- Spot: "BTCUSDT", "ETHUSDT", "SOLUSDT"
- Perpetuals: "BTCUSDT.P", "ETHUSDT.P", "SOLUSDT.P"
- Note: Perpetuals have ".P" suffix

### CCXT Library (for WebSocket/API)
- Spot: "BTC/USDT", "ETH/USDT", "SOL/USDT"
- Perpetuals: "BTC/USDT:USDT", "ETH/USDT:USDT" (with quote currency after colon)
- Format: "BASE/QUOTE" or "BASE/QUOTE:SETTLE"
- Note: Uses slash separator and uppercase

### Binance Exchange (Native Format)
- Spot: "BTCUSDT", "ETHUSDT" (no separator)
- Futures USDT-M: "BTCUSDT" (same as spot)
- Futures COIN-M: "BTCUSD_PERP" (inverse perpetuals)
- **CCXT Format for Perpetuals**: "BTC/USDT:USDT"
- Note: CCXT normalizes to "BASE/QUOTE:SETTLE" for perpetual contracts

### Bybit Exchange (Native Format)
- Spot: "BTCUSDT", "ETHUSDT"
- Linear Perpetuals: "BTCUSDT" (USDT-margined)
- Inverse Perpetuals: "BTCUSD" (coin-margined)
- **CCXT Format for Perpetuals**: "BTC/USDT:USDT" (linear), "BTC/USD:BTC" (inverse)
- Note: Our system uses :USDT suffix for all USDT-margined perpetuals

### MEXC Exchange (Native Format)
- Spot: "BTC_USDT", "ETH_USDT" (underscore separator)
- Perpetuals: "BTC_USDT" (same format as spot)
- **CCXT Format for Perpetuals**: "BTC/USDT:USDT"
- Note: CCXT handles format conversion, requires protobuf library for WebSocket

### Bitget Exchange
- Spot: "BTCUSDT_SPBL"
- Perpetuals: "BTCUSDT_UMCBL" (USDT-M contracts)
- Note: Uses suffix for product type

## NORMALIZATION STRATEGY ##

1. **Input**: Accept TradingView format (e.g., "HIPPOUSDT.P")
2. **Strip Suffixes**: Remove ".P", ".PERP", "-PERP" to get base symbol
3. **Parse Base/Quote**: Split "HIPPOUSDT" → "HIPPO" + "USDT"
4. **CCXT Format**: Create "HIPPO/USDT" for CCXT library
5. **Exchange-Specific**: Let CCXT handle exchange-specific formatting

## EDGE CASES ##

- **Small/Micro Caps**: May not be on all exchanges (try Bybit, MEXC, Bitget)
- **Stablecoins**: USDT, USDC, BUSD, DAI - handle all quote currencies
- **BTC Pairs**: BTC as quote (e.g., "ETH/BTC")
- **Fiat Pairs**: EUR, USD (not common in crypto)
- **Perpetual Detection**: ".P" suffix indicates perpetual contract
"""
import re
from typing import Tuple, Optional


def normalize_symbol(tradingview_symbol: str) -> Tuple[str, str, bool]:
    """
    Normalize TradingView symbol to CCXT format

    Args:
        tradingview_symbol: Symbol from TradingView (e.g., "BTCUSDT", "HIPPOUSDT.P")

    Returns:
        Tuple of (ccxt_symbol, base_asset, is_perpetual)
        - ccxt_symbol: Format for CCXT (e.g., "BTC/USDT", "HIPPO/USDT")
        - base_asset: Base asset (e.g., "BTC", "HIPPO")
        - is_perpetual: True if perpetual contract

    Examples:
        "BTCUSDT" → ("BTC/USDT", "BTC", False)
        "BTCUSDT.P" → ("BTC/USDT", "BTC", True)
        "HIPPOUSDT.P" → ("HIPPO/USDT", "HIPPO", True)
        "ETHUSDC" → ("ETH/USDC", "ETH", False)
    """
    # Remove common perpetual suffixes
    is_perpetual = False
    original = tradingview_symbol

    if tradingview_symbol.endswith('.P'):
        tradingview_symbol = tradingview_symbol[:-2]
        is_perpetual = True
    elif tradingview_symbol.endswith('.PERP'):
        tradingview_symbol = tradingview_symbol[:-5]
        is_perpetual = True
    elif tradingview_symbol.endswith('-PERP'):
        tradingview_symbol = tradingview_symbol[:-5]
        is_perpetual = True
    elif tradingview_symbol.endswith('PERP'):
        tradingview_symbol = tradingview_symbol[:-4]
        is_perpetual = True

    # Now we have something like "BTCUSDT", "HIPPOUSDT", "ETHUSDC"
    # Need to split into base/quote

    # Common quote currencies (in order of priority - longer matches first)
    quote_currencies = ['USDT', 'USDC', 'BUSD', 'USD', 'EUR', 'BTC', 'ETH']

    base = None
    quote = None

    for quote_currency in quote_currencies:
        if tradingview_symbol.endswith(quote_currency):
            quote = quote_currency
            base = tradingview_symbol[:-len(quote_currency)]
            break

    if not base or not quote:
        raise ValueError(f"Unable to parse symbol: {original}")

    # Create CCXT format
    # For perpetual contracts, add settlement currency (e.g., "BTC/USDT:USDT")
    if is_perpetual:
        ccxt_symbol = f"{base}/{quote}:{quote}"  # e.g., "BTC/USDT:USDT" for perps
    else:
        ccxt_symbol = f"{base}/{quote}"  # e.g., "BTC/USDT" for spot

    return ccxt_symbol, base, is_perpetual


def get_display_symbol(tradingview_symbol: str) -> str:
    """
    Get clean display symbol (for UI/logs)

    Args:
        tradingview_symbol: Original symbol from TradingView

    Returns:
        Clean symbol for display (e.g., "BTCUSDT", "HIPPOUSDT")

    Examples:
        "BTCUSDT.P" → "BTCUSDT"
        "HIPPOUSDT.P" → "HIPPOUSDT"
    """
    # Remove perpetual suffixes
    symbol = tradingview_symbol

    for suffix in ['.P', '.PERP', '-PERP', 'PERP']:
        if symbol.endswith(suffix):
            return symbol[:-len(suffix)]

    return symbol


def detect_exchange_from_symbol(symbol: str) -> Optional[str]:
    """
    Attempt to detect the best exchange for a symbol

    Args:
        symbol: CCXT format symbol (e.g., "BTC/USDT")

    Returns:
        Exchange name or None

    Note: This is a heuristic, not perfect
    """
    base, quote = symbol.split('/')

    # Major coins - prefer Binance
    major_coins = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'MATIC', 'DOT', 'AVAX']
    if base in major_coins:
        return 'binance'

    # Small/micro caps - try Bybit or MEXC
    return 'bybit'


if __name__ == "__main__":
    # Test cases
    test_symbols = [
        "BTCUSDT",
        "BTCUSDT.P",
        "HIPPOUSDT.P",
        "ETHUSDC",
        "SOLUSDT.P",
    ]

    print("Symbol Normalization Tests:")
    print("-" * 60)

    for symbol in test_symbols:
        try:
            ccxt_symbol, base, is_perp = normalize_symbol(symbol)
            display = get_display_symbol(symbol)
            exchange = detect_exchange_from_symbol(ccxt_symbol)

            print(f"{symbol:20s} → {ccxt_symbol:15s} (base: {base:10s}, perp: {is_perp}, exchange: {exchange})")
            print(f"{'':20s}   Display: {display}")
            print()
        except Exception as e:
            print(f"{symbol:20s} → ERROR: {e}")
            print()
