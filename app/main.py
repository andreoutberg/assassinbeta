"""
Andre Assassin High-WR Trading System - FastAPI Backend
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging
from datetime import datetime
from typing import Optional

from app.config import settings
from app.services.price_tracker import PriceTracker
from app.services.statistics_engine import StatisticsEngine
from app.services.bybit_client import BybitClient
from app.services.market_data_service import MarketDataService
from app.services.signal_generator import SignalGenerator
from app.services.phase_manager import PhaseManager
from app.services.websocket_manager import WebSocketManager
from app.services.metrics import metrics_service
from app.database.database import AsyncSessionLocal
from app.database.connection import DatabaseManager, redis_client, init_redis

# Configure comprehensive logging for weekend monitoring
from logging_config import setup_logging

# Setup rotating logs with detailed output
setup_logging()

logger = logging.getLogger(__name__)

# Global service instances
price_tracker: Optional[PriceTracker] = None
statistics_engine: Optional[StatisticsEngine] = None
db_manager: Optional[DatabaseManager] = None
bybit_client: Optional[BybitClient] = None
market_data_service: Optional[MarketDataService] = None
signal_generator: Optional[SignalGenerator] = None
phase_manager: Optional[PhaseManager] = None
ws_manager: Optional[WebSocketManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - initialize services on startup"""
    global price_tracker, statistics_engine, db_manager, bybit_client, market_data_service
    global signal_generator, phase_manager, ws_manager

    # ==================== STARTUP ====================
    logger.info("🚀 Andre Assassin High-WR Trading System starting up...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Initialize database manager
    logger.info("🗄️ Initializing DatabaseManager...")
    db_manager = DatabaseManager()
    await db_manager.initialize()

    # Initialize Redis cache
    logger.info("📦 Initializing Redis cache...")
    await init_redis()

    # Initialize Bybit client
    logger.info("💱 Initializing Bybit client...")
    bybit_client = BybitClient(
        api_key=getattr(settings, 'BYBIT_API_KEY', ''),
        api_secret=getattr(settings, 'BYBIT_API_SECRET', ''),
        testnet=getattr(settings, 'BYBIT_TESTNET', True)
    )

    # Initialize services
    logger.info("📡 Initializing PriceTracker...")
    price_tracker = PriceTracker()

    logger.info("📊 Initializing StatisticsEngine...")
    statistics_engine = StatisticsEngine()

    logger.info("📈 Initializing MarketDataService...")
    market_data_service = MarketDataService(bybit_client)

    logger.info("🔔 Initializing SignalGenerator...")
    signal_generator = SignalGenerator(market_data_service)

    logger.info("🎯 Initializing PhaseManager...")
    phase_manager = PhaseManager()

    logger.info("🔌 Initializing WebSocketManager...")
    ws_manager = WebSocketManager()

    # Store instances in app state for access in routes
    app.state.db_manager = db_manager
    app.state.bybit_client = bybit_client
    app.state.market_data_service = market_data_service
    app.state.signal_generator = signal_generator
    app.state.phase_manager = phase_manager
    app.state.ws_manager = ws_manager
    app.state.price_tracker = price_tracker
    app.state.statistics_engine = statistics_engine

    # Register services with routes
    from app.api import api_routes
    api_routes.init_services(price_tracker, statistics_engine)
    logger.info("✅ Services initialized and registered")

    # Start background services
    logger.info("🚀 Starting background services...")
    # await market_data_service.start()  # Method does not exist
    # await signal_generator.start()  # Method does not exist

    # Start WebSocket tracking for active trades (in background)
    logger.info("🔌 Starting WebSocket tracking for active trades...")

    async def start_tracking_bg():
        async with AsyncSessionLocal() as db:
            await price_tracker._load_active_trades(db)

            # CRITICAL: Load markets before subscribing (CCXT requirement)
            await price_tracker.websocket_manager.load_markets_async()

            # Subscribe to WebSocket feeds (multiplexed - 1 connection per symbol)
            for symbol in price_tracker.subscriptions.keys():
                callback = await price_tracker._create_price_callback(symbol)
                await price_tracker.websocket_manager.subscribe(symbol, callback)
                logger.info(f"📡 Subscribed to {symbol} (trades: {len(price_tracker.subscriptions[symbol])})")

            # Mark price tracker as running
            price_tracker.running = True
            logger.info(f"✅ Price tracker active: {len(price_tracker.active_trades)} trades, {len(price_tracker.subscriptions)} symbols")

    # Run in background task
    asyncio.create_task(start_tracking_bg())

    logger.info("✅ Andre Assassin High-WR Trading System started successfully!")

    # ==================== RUNNING ====================
    yield

    # ==================== SHUTDOWN ====================
    logger.info("🛑 Andre Assassin High-WR Trading System shutting down...")

    # Stop background services
    # if market_data_service:
    #     await market_data_service.stop()  # Method does not exist
    # if signal_generator:
    #     await signal_generator.stop()  # Method does not exist

    if price_tracker:
        logger.info("📡 Stopping WebSocket tracking...")
        price_tracker.running = False

        # Force commit any pending batches
        async with AsyncSessionLocal() as db:
            await price_tracker._force_commit_batch(db)

    # Close connections
    if db_manager:
        await db_manager.close()
    if redis_client:
        await redis_client.close()
    if ws_manager:
        await ws_manager.disconnect_all()

    logger.info("✅ Andre Assassin High-WR Trading System shut down successfully")


# Create FastAPI application
app = FastAPI(
    title="Andre Assassin High-WR Trading System",
    description="High Win-Rate Crypto Trading System with Advanced Strategy Management",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Configure CORS for AO Dashboard integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trusted host middleware for security
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=getattr(settings, 'ALLOWED_HOSTS', ["*"])
)

# Mount static files for dashboard
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Andre Assassin API",
        "version": "1.0.0",
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "health": "/api/health",
            "docs": "/docs",
            "webhook": "/api/webhook/tradingview",
            "analysis": "/api/analysis",
            "integration": "/api/integration",
            "dashboard": "/dashboard"
        }
    }


@app.get("/dashboard")
async def dashboard():
    """Serve the improved dashboard"""
    dashboard_path = static_dir / "improved_dashboard.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path)
    else:
        return JSONResponse(
            status_code=404,
            content={
                "error": "Dashboard not found",
                "message": "Dashboard file does not exist",
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@app.get("/beta")
async def beta_dashboard():
    """Serve the beta dashboard"""
    beta_path = static_dir / "beta.html"
    if beta_path.exists():
        return FileResponse(beta_path)
    else:
        return JSONResponse(
            status_code=404,
            content={
                "error": "Beta dashboard not found",
                "message": "Beta dashboard file does not exist",
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@app.get("/phase2")
async def phase2_dashboard():
    """Serve the Phase II Dashboard"""
    dashboard_path = static_dir / "phase2_dashboard.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path)
    else:
        return JSONResponse(
            status_code=404,
            content={
                "error": "Phase II Dashboard not found",
                "message": "Phase II dashboard file does not exist",
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "services": {
            "api": "operational",
            "database": "pending_implementation",  # TODO: Add database health check
            "ai_analysis": "pending_implementation"  # TODO: Add AI service health check
        }
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import CONTENT_TYPE_LATEST
    from app.services.metrics import metrics_service
    return JSONResponse(
        content=metrics_service.get_metrics().decode('utf-8'),
        media_type=CONTENT_TYPE_LATEST
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": f"Endpoint {request.url.path} not found",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Global HTTPException handler
    Returns structured error responses without leaking implementation details
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if exc.status_code < 500 else "Internal Server Error",
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.url.path
        },
        headers=exc.headers
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Global generic exception handler
    Logs full error details but returns safe error response to client
    """
    import traceback

    # Log full error details for debugging (with stack trace)
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else "unknown"
        }
    )

    # Write to file for critical errors (optional - can be removed if logs are centralized)
    try:
        with open("/tmp/webhook_error.log", "a") as f:
            f.write(f"\n\n=== UNHANDLED ERROR {datetime.utcnow()} ===\n")
            f.write(f"Method: {request.method}\n")
            f.write(f"Path: {request.url.path}\n")
            f.write(f"Error: {exc}\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception as log_error:
        logger.error(f"Failed to write error log: {log_error}")

    # Return safe error response (NO stack traces or sensitive info)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please contact support if this persists.",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.headers.get("X-Request-ID", "unknown")
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Custom 500 handler (legacy - kept for backwards compatibility)"""
    # This will be overridden by the generic Exception handler above
    return await generic_exception_handler(request, exc)


# Include existing API routers
from app.api.api_routes import router as api_router
from app.api.strategy_routes import router as strategy_router

# Include new API routers
# from app.api.routes.demo_trading import router as demo_trading_router  # Missing DemoPosition, DemoAccount models
# from app.api.routes.signals import router as signals_router  # Missing SignalPerformance model
# from app.api.routes.strategies import router as strategies_router  # File does not exist yet
# from app.api.routes.market_data import router as market_data_router  # File does not exist yet
# from app.api.routes.config import router as config_router  # File does not exist yet
from app.api.routes.websocket import router as websocket_router
from app.api.routes.beta_api import router as beta_api_router

# Register existing routers
app.include_router(api_router, prefix="/api")
app.include_router(strategy_router, prefix="/api")

# Register new routers
# app.include_router(demo_trading_router, prefix="/api/demo", tags=["Demo Trading"])
# app.include_router(signals_router, prefix="/api/signals", tags=["Signals"])
# app.include_router(strategies_router, prefix="/api/strategies", tags=["Strategies"])
# app.include_router(market_data_router, prefix="/api/market", tags=["Market Data"])
# app.include_router(config_router, prefix="/api/config", tags=["Configuration"])
app.include_router(websocket_router, tags=["WebSocket"])
app.include_router(beta_api_router, prefix="/api", tags=["Beta Dashboard"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.WEBHOOK_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )
