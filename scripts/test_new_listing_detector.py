#!/usr/bin/env python3
"""
Test script for New Listing Detector

This script demonstrates how to use the new listing detector
and test its functionality.
"""

import asyncio
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.new_listing_detector import NewListingDetector, NewListingEvent
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_basic_functionality():
    """Test basic detector functionality"""
    logger.info("Testing New Listing Detector basic functionality...")

    # Create detector (without Redis for testing)
    detector = NewListingDetector(
        redis_host='localhost',
        webhook_url="http://localhost:8000/api/webhook/tradingview"
    )

    # Add test callback
    detected_listings = []

    async def test_callback(event: NewListingEvent):
        detected_listings.append(event)
        logger.info(f"Test callback triggered: {event.symbol} on {event.exchange}")

    detector.add_callback(test_callback)

    # Initialize detector
    await detector.initialize()

    # Print initial stats
    stats = detector.get_stats()
    logger.info(f"Initial known symbols count:")
    for exchange, count in stats['known_symbols_count'].items():
        logger.info(f"  {exchange}: {count} symbols")

    return detector, detected_listings


async def test_rest_detection():
    """Test REST API detection"""
    logger.info("\nTesting REST API detection...")

    detector = NewListingDetector()
    await detector.initialize()

    # Manually check for new symbols
    logger.info("Checking Binance futures...")
    exchange = detector.rest_exchanges.get('binance')
    if exchange:
        markets = exchange.fetch_markets()
        futures = [m for m in markets if m['type'] in ['swap', 'future']]
        logger.info(f"Found {len(futures)} Binance futures contracts")

    logger.info("Checking Upbit KRW pairs...")
    exchange = detector.rest_exchanges.get('upbit')
    if exchange:
        markets = exchange.fetch_markets()
        krw_pairs = [m for m in markets if m['quote'] == 'KRW']
        logger.info(f"Found {len(krw_pairs)} Upbit KRW pairs")

    return detector


async def test_websocket_connection():
    """Test WebSocket connections"""
    logger.info("\nTesting WebSocket connections...")

    detector = NewListingDetector()
    await detector.initialize()

    # Test Binance WebSocket
    if 'binance' in detector.ws_exchanges:
        logger.info("Testing Binance WebSocket...")
        try:
            exchange = detector.ws_exchanges['binance']
            await exchange.load_markets()
            logger.info("✅ Binance WebSocket connection successful")
        except Exception as e:
            logger.error(f"❌ Binance WebSocket error: {e}")

    # Test Bybit WebSocket
    if 'bybit' in detector.ws_exchanges:
        logger.info("Testing Bybit WebSocket...")
        try:
            exchange = detector.ws_exchanges['bybit']
            await exchange.load_markets()
            logger.info("✅ Bybit WebSocket connection successful")
        except Exception as e:
            logger.error(f"❌ Bybit WebSocket error: {e}")

    return detector


async def run_detector_for_duration(duration_seconds: int = 60):
    """Run detector for a specified duration"""
    logger.info(f"\nRunning detector for {duration_seconds} seconds...")

    detector = NewListingDetector(
        webhook_url="http://localhost:8000/api/webhook/tradingview"
    )

    # Add monitoring callback
    async def monitor_callback(event: NewListingEvent):
        logger.warning(f"🚨 DETECTED: {event.symbol} on {event.exchange}")

    detector.add_callback(monitor_callback)

    # Start detector in background
    detector_task = asyncio.create_task(detector.start())

    # Wait for specified duration
    await asyncio.sleep(duration_seconds)

    # Stop detector
    await detector.stop()

    # Get final stats
    stats = detector.get_stats()
    logger.info("\nFinal Statistics:")
    logger.info(f"  Total detections: {stats['total_detections']}")
    logger.info(f"  REST polls: {stats['rest_polls']}")
    logger.info(f"  WebSocket reconnects: {stats['websocket_reconnects']}")

    return detector


async def simulate_new_listing():
    """Simulate a new listing detection"""
    logger.info("\nSimulating new listing detection...")

    detector = NewListingDetector()

    # Create a fake event
    fake_event = NewListingEvent(
        exchange='binance',
        symbol='FAKE/USDT',
        price=0.0001,
        volume=1000000,
        timestamp=asyncio.get_event_loop().time(),
        source='test',
        metadata={'test': True}
    )

    # Process the fake event
    await detector._handle_new_listing(fake_event)

    logger.info("Simulation complete")


async def main():
    """Main test function"""
    logger.info("=" * 60)
    logger.info("NEW LISTING DETECTOR TEST SUITE")
    logger.info("=" * 60)

    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Test New Listing Detector')
    parser.add_argument('--test', choices=['basic', 'rest', 'websocket', 'run', 'simulate'],
                       default='basic', help='Test to run')
    parser.add_argument('--duration', type=int, default=60,
                       help='Duration to run detector (seconds)')
    args = parser.parse_args()

    try:
        if args.test == 'basic':
            detector, listings = await test_basic_functionality()

        elif args.test == 'rest':
            detector = await test_rest_detection()

        elif args.test == 'websocket':
            detector = await test_websocket_connection()

        elif args.test == 'run':
            detector = await run_detector_for_duration(args.duration)

        elif args.test == 'simulate':
            await simulate_new_listing()

        logger.info("\n✅ Test completed successfully")

    except KeyboardInterrupt:
        logger.info("\n⚠️ Test interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())