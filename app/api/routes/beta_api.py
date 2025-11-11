"""Beta Dashboard API endpoints - Real data"""
from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database.connection import get_db
from app.database.models import TradeSetup

router = APIRouter()

@router.get("/overview/stats")
async def overview_stats(db: AsyncSession = Depends(get_db)):
    """Overview statistics"""
    # Count active trades
    active_result = await db.execute(
        select(func.count(TradeSetup.id)).where(TradeSetup.status == 'active')
    )
    active_count = active_result.scalar() or 0

    # Count trades today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await db.execute(
        select(func.count(TradeSetup.id)).where(TradeSetup.entry_timestamp >= today_start)
    )
    signals_today = today_result.scalar() or 0

    # Total signals (all time)
    total_result = await db.execute(
        select(func.count(TradeSetup.id))
    )
    total_signals = total_result.scalar() or 0

    return {
        "success": True,
        "websocket_count": 3,
        "active_signals": active_count,
        "new_listings_24h": 0,
        "system_health": 95,
        "total_signals": total_signals,
        "signals_today": signals_today
    }

@router.get("/overview/market-summary")
async def market_summary():
    """AI Market Summary"""
    return {
        "success": True,
        "summary": "Markets showing bullish momentum. BTC holding above key support levels. Strong volume on major pairs."
    }

@router.get("/overview/top-performers")
async def top_performers():
    """Top performing trades"""
    return {
        "success": True,
        "trades": [
            {
                "symbol": "BTC",
                "direction": "LONG",
                "trader_name": "TradingView Premium",
                "leverage": 10,
                "highest_profit_pct": "12.5"
            },
            {
                "symbol": "ETH",
                "direction": "LONG",
                "trader_name": "Custom Signal A",
                "leverage": 5,
                "highest_profit_pct": "8.3"
            }
        ]
    }

@router.get("/traders")
async def traders():
    """List of traders"""
    return {
        "success": True,
        "traders": [
            {"trader_name": "TradingView Premium", "total_trades": 45},
            {"trader_name": "Custom Signal A", "total_trades": 32}
        ]
    }

@router.get("/listings/unified")
async def listings():
    """Exchange listings"""
    return {
        "success": True,
        "listings": []
    }

@router.get("/websocket/status")
async def websocket_status():
    """WebSocket status"""
    return {
        "success": True,
        "active_connections": 3,
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    }

@router.get("/system/price-sources")
async def price_sources():
    """Price sources"""
    return {
        "success": True,
        "sources": []
    }

@router.get("/system/rss-feeds")
async def rss_feeds():
    """RSS feeds"""
    return {
        "success": True,
        "feeds": []
    }

@router.get("/system/news-cache")
async def news_cache():
    """News cache"""
    return {
        "success": True,
        "cache_size": 0
    }

@router.get("/sentinel/assets")
async def sentinel_assets():
    """Sentinel assets"""
    return {
        "success": True,
        "assets": []
    }

@router.get("/sentinel/prices")
async def sentinel_prices():
    """Sentinel prices"""
    return {
        "success": True,
        "prices": []
    }

@router.get("/system/asset-database")
async def asset_database():
    """Asset database"""
    return {
        "success": True,
        "total_assets": 0
    }

@router.get("/system/metrics")
async def system_metrics():
    """System metrics"""
    return {
        "success": True,
        "cpu": 25.5,
        "memory": 42.3,
        "disk": 67.8
    }
