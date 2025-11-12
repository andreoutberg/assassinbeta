# New Listing Detector Implementation Guide

## Overview

The New Listing Detector is a production-ready system for detecting new cryptocurrency listings across major exchanges in real-time. It uses a hybrid approach combining WebSocket streams for speed and REST API polling for reliability.

## Supported Exchanges

| Exchange | Market Type | Detection Method | Expected Latency |
|----------|-------------|------------------|------------------|
| **Binance** | USDT Perpetual Futures | CCXT Pro WebSocket | 1-3 seconds |
| **Bybit** | USDT Perpetual Futures | CCXT Pro WebSocket | 1-3 seconds |
| **Upbit** | KRW Spot Pairs | Direct WebSocket | <0.5 seconds |
| **MEXC** | USDT Perpetual Futures | REST API (isNew flag) | 30-60 seconds |

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements_listing_detector.txt
```

### 2. Basic Usage

```python
from app.services.new_listing_detector import NewListingDetector

# Create detector
detector = NewListingDetector(
    redis_host='localhost',
    webhook_url="http://localhost:8000/api/webhook/tradingview"
)

# Start detection
await detector.start()
```

### 3. Run Test Script

```bash
# Test basic functionality
python scripts/test_new_listing_detector.py --test basic

# Test REST API detection
python scripts/test_new_listing_detector.py --test rest

# Test WebSocket connections
python scripts/test_new_listing_detector.py --test websocket

# Run detector for 5 minutes
python scripts/test_new_listing_detector.py --test run --duration 300
```

## Architecture

```
┌─────────────────────────────────────────┐
│          NEW LISTING DETECTOR           │
├─────────────────────────────────────────┤
│                                         │
│  WebSocket Streams (Primary):           │
│  • Binance Futures (CCXT Pro)          │
│  • Bybit Futures (CCXT Pro)            │
│  • Upbit Spot (Direct WebSocket)       │
│                                         │
│  REST API Polling (Backup):            │
│  • All exchanges every 5 minutes       │
│  • MEXC isNew flag check               │
│                                         │
│  Persistence:                           │
│  • Redis for known symbols             │
│  • Deduplication cache                 │
│                                         │
│  Notifications:                         │
│  • Webhook to trading system           │
│  • Custom callbacks                    │
└─────────────────────────────────────────┘
```

## Key Features

### 1. CCXT Integration
- Unified interface for multiple exchanges
- Automatic rate limiting
- Built-in error handling

### 2. Real-Time Detection
- WebSocket streams for sub-second detection
- Particularly fast for Upbit (<0.5s)

### 3. Reliability
- Automatic reconnection with exponential backoff
- REST API backup polling
- Redis persistence across restarts

### 4. Deduplication
- Prevents duplicate detections
- 1-minute cache for recent detections

### 5. Special Handling

#### Upbit (Critical)
- Direct WebSocket for fastest detection
- KRW pairs only
- Sends LONG-only signals (typical pump behavior)
- Alert for extreme volatility (50-200% possible)

#### MEXC
- Checks explicit `isNew` flag
- Most reliable new listing indicator

## Configuration

### Environment Variables
```bash
# Redis connection
REDIS_HOST=localhost
REDIS_PORT=6379

# Webhook endpoint
WEBHOOK_URL=http://localhost:8000/api/webhook/tradingview

# Polling intervals
REST_POLL_INTERVAL=300  # 5 minutes
```

### Custom Callbacks

Add custom handlers for new listing events:

```python
async def my_handler(event: NewListingEvent):
    print(f"New listing: {event.symbol} on {event.exchange}")
    print(f"Price: {event.price}, Volume: {event.volume}")

    # Your custom logic here
    if event.exchange == 'upbit':
        # Special handling for Upbit
        send_urgent_alert(event)

detector.add_callback(my_handler)
```

## Webhook Format

The detector sends webhooks in this format:

```json
{
  "symbol": "BTCUSDT",
  "direction": "LONG",
  "source": "new_listing_binance",
  "timeframe": "5m",
  "metadata": {
    "reason": "new_listing_detected",
    "exchange": "binance",
    "detection_source": "websocket",
    "detection_price": 50000.0,
    "detection_volume": 1000000.0
  }
}
```

## Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements_listing_detector.txt .
RUN pip install -r requirements_listing_detector.txt

# Copy detector
COPY app/services/new_listing_detector.py ./app/services/

# Run detector
CMD ["python", "-m", "app.services.new_listing_detector"]
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| CPU Usage | ~5% (single core) |
| Memory Usage | ~200MB |
| Network Usage | ~100KB/s |
| Detection Latency (WebSocket) | 1-3 seconds |
| Detection Latency (Upbit) | <0.5 seconds |
| Detection Latency (REST) | 30-60 seconds |

## Monitoring

The detector provides statistics via `get_stats()`:

```python
stats = detector.get_stats()
print(f"Total detections: {stats['total_detections']}")
print(f"Detections by exchange: {stats['detections_by_exchange']}")
print(f"WebSocket reconnects: {stats['websocket_reconnects']}")
print(f"REST polls: {stats['rest_polls']}")
```

## Troubleshooting

### Issue: No detections
- Check Redis connection
- Verify exchanges are accessible
- Check network connectivity
- Review logs for errors

### Issue: Duplicate detections
- Ensure Redis is running
- Check deduplication cache
- Verify single instance running

### Issue: WebSocket disconnections
- Normal behavior (auto-reconnects)
- Check for rate limiting
- Verify API credentials (if using private endpoints)

### Issue: High latency
- Switch to direct WebSocket for critical exchanges
- Reduce REST polling interval
- Check network latency to exchange servers

## Important Notes

1. **Upbit Impact**: Upbit listings often cause 50-200% price movements within minutes. Fast detection is critical.

2. **False Positives**: On first run, all current symbols are loaded as "known" to prevent false positives.

3. **Volume Verification**: Only symbols with actual trading volume are reported as new listings.

4. **Rate Limits**: CCXT handles rate limits automatically when `enableRateLimit: True`.

5. **Persistence**: Redis stores known symbols to survive restarts without false positives.

## Files

- `/docs/NEW_LISTING_DETECTION_COMPREHENSIVE.md` - Full research document
- `/docs/NEW_LISTING_DETECTION_RESEARCH.md` - Original research
- `/app/services/new_listing_detector.py` - Main implementation
- `/scripts/test_new_listing_detector.py` - Test script
- `/requirements_listing_detector.txt` - Dependencies

## Support

For issues or improvements, check the comprehensive research document at `/docs/NEW_LISTING_DETECTION_COMPREHENSIVE.md`