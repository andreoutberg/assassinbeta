"""
SQLAlchemy models for High-WR Trading System
"""
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Boolean,
    ForeignKey, Enum as SQLEnum, Text, DECIMAL, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
import uuid

from app.database.connection import Base


class PositionStatus(str, enum.Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ERROR = "error"


class PositionDirection(str, enum.Enum):
    LONG = "long"
    SHORT = "short"


class SignalType(str, enum.Enum):
    ENTRY = "entry"
    EXIT = "exit"
    REVERSAL = "reversal"
    CONTINUATION = "continuation"
    BREAKOUT = "breakout"
    SCALP = "scalp"


class SignalSource(str, enum.Enum):
    MOMENTUM = "momentum"
    PATTERN = "pattern"
    VOLUME = "volume"
    VOLATILITY = "volatility"
    ML_MODEL = "ml_model"
    COMBINED = "combined"


class StrategyPhase(str, enum.Enum):
    PHASE_1 = "phase_1"
    PHASE_2 = "phase_2"
    PHASE_3 = "phase_3"
    OPTIMIZATION = "optimization"
    PRODUCTION = "production"


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(DECIMAL(18, 8), nullable=False)
    bid_price = Column(DECIMAL(18, 8))
    ask_price = Column(DECIMAL(18, 8))
    volume = Column(DECIMAL(20, 8), nullable=False, default=0)
    volatility = Column(DECIMAL(10, 4), nullable=False, default=0)
    atr = Column(DECIMAL(18, 8))  # Average True Range
    rsi = Column(DECIMAL(5, 2))  # Relative Strength Index
    metadata = Column(JSONB, default={})
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('idx_market_prices_symbol_timestamp', 'symbol', 'timestamp'),
        Index('idx_market_prices_volatility', 'volatility', postgresql_where=(volatility > 0)),
    )


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(SQLEnum(PositionDirection), nullable=False)
    tp_pct = Column(DECIMAL(5, 2), nullable=False)
    sl_pct = Column(DECIMAL(5, 2), nullable=False)
    trailing_config = Column(JSONB, default={"enabled": False, "activation_pct": 1.5, "trail_pct": 0.5})
    breakeven_pct = Column(DECIMAL(5, 2), default=1.0)
    win_rate = Column(DECIMAL(5, 2), default=0)
    rr_ratio = Column(DECIMAL(5, 2), default=1.5)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    avg_pnl = Column(DECIMAL(10, 2), default=0)
    max_drawdown = Column(DECIMAL(10, 2), default=0)
    sharpe_ratio = Column(DECIMAL(5, 2))
    simulations = Column(Integer, default=0)
    phase = Column(SQLEnum(StrategyPhase), nullable=False, default=StrategyPhase.PHASE_1)
    optimization_params = Column(JSONB, default={})
    active = Column(Boolean, default=True, index=True)
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    demo_positions = relationship("DemoPosition", back_populates="strategy")
    demo_trades = relationship("DemoTrade", back_populates="strategy")

    __table_args__ = (
        Index('idx_strategies_symbol_direction', 'symbol', 'direction'),
        Index('idx_strategies_win_rate_active', 'win_rate', 'active'),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(SQLEnum(PositionDirection), nullable=False)
    entry_price = Column(DECIMAL(18, 8), nullable=False)
    signal_type = Column(SQLEnum(SignalType), nullable=False)
    source = Column(SQLEnum(SignalSource), nullable=False)
    confidence = Column(DECIMAL(5, 2), nullable=False)
    strength = Column(DECIMAL(5, 2), default=50)
    indicators = Column(JSONB, default={})
    target_tp = Column(DECIMAL(18, 8))
    target_sl = Column(DECIMAL(18, 8))
    expected_rr = Column(DECIMAL(5, 2))
    volume_confirmation = Column(Boolean, default=False)
    pattern_name = Column(String(100))
    timeframe = Column(String(10), default='5m')
    expires_at = Column(DateTime(timezone=True))
    metadata = Column(JSONB, default={})
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    demo_positions = relationship("DemoPosition", back_populates="signal")
    demo_trades = relationship("DemoTrade", back_populates="signal")

    __table_args__ = (
        Index('idx_signals_symbol_timestamp', 'symbol', 'timestamp'),
        Index('idx_signals_confidence_desc', 'confidence'),
        Index('idx_signals_symbol_direction_timestamp', 'symbol', 'direction', 'timestamp'),
    )


class DemoPosition(Base):
    __tablename__ = "demo_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id = Column(String(100), unique=True, nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(SQLEnum(PositionDirection), nullable=False)
    entry_price = Column(DECIMAL(18, 8), nullable=False)
    current_price = Column(DECIMAL(18, 8))
    tp_price = Column(DECIMAL(18, 8), nullable=False)
    sl_price = Column(DECIMAL(18, 8), nullable=False)
    size = Column(DECIMAL(18, 8), nullable=False)
    status = Column(SQLEnum(PositionStatus), nullable=False, default=PositionStatus.PENDING, index=True)
    pnl = Column(DECIMAL(18, 2), default=0)
    pnl_pct = Column(DECIMAL(10, 4), default=0)
    fees = Column(DECIMAL(10, 4), default=0)
    signal_id = Column(UUID(as_uuid=True), ForeignKey('signals.id', ondelete='SET NULL'))
    strategy_id = Column(UUID(as_uuid=True), ForeignKey('strategies.id', ondelete='SET NULL'))
    trailing_activated = Column(Boolean, default=False)
    trailing_sl_price = Column(DECIMAL(18, 8))
    breakeven_activated = Column(Boolean, default=False)
    max_profit = Column(DECIMAL(18, 2), default=0)
    max_loss = Column(DECIMAL(18, 2), default=0)
    exit_reason = Column(String(100))
    metadata = Column(JSONB, default={})
    opened_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    signal = relationship("Signal", back_populates="demo_positions")
    strategy = relationship("Strategy", back_populates="demo_positions")
    demo_trade = relationship("DemoTrade", back_populates="position", uselist=False)

    __table_args__ = (
        Index('idx_demo_positions_open', 'symbol', 'status', postgresql_where=(status == 'open')),
        Index('idx_demo_positions_pnl_closed', 'pnl', postgresql_where=(status == 'closed')),
    )


class DemoTrade(Base):
    __tablename__ = "demo_trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id = Column(UUID(as_uuid=True), ForeignKey('demo_positions.id', ondelete='CASCADE'), nullable=False)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey('strategies.id', ondelete='CASCADE'), nullable=False)
    signal_id = Column(UUID(as_uuid=True), ForeignKey('signals.id', ondelete='SET NULL'))
    entry_price = Column(DECIMAL(18, 8), nullable=False)
    exit_price = Column(DECIMAL(18, 8))
    pnl = Column(DECIMAL(18, 2), default=0)
    pnl_pct = Column(DECIMAL(10, 4), default=0)
    duration_seconds = Column(Integer)
    is_winner = Column(Boolean)
    rr_achieved = Column(DECIMAL(5, 2))
    max_adverse_excursion = Column(DECIMAL(10, 4))  # MAE
    max_favorable_excursion = Column(DECIMAL(10, 4))  # MFE
    exit_type = Column(String(50))  # 'tp', 'sl', 'trailing', 'manual', 'timeout'
    metadata = Column(JSONB, default={})
    executed_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    position = relationship("DemoPosition", back_populates="demo_trade")
    strategy = relationship("Strategy", back_populates="demo_trades")
    signal = relationship("Signal", back_populates="demo_trades")

    __table_args__ = (
        Index('idx_demo_trades_strategy_performance', 'strategy_id', 'is_winner', 'pnl_pct'),
    )


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(JSONB, nullable=False)
    category = Column(String(50), default='general', index=True)
    description = Column(Text)
    is_secret = Column(Boolean, default=False)
    is_readonly = Column(Boolean, default=False)
    validation_schema = Column(JSONB)
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100))