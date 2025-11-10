"""
Baseline Database Models for AI Andre

Tracks baseline performance of signals without TP/SL exits.
Trades close only when replaced by new signals from same webhook source.
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class BaselineTrade(Base):
    """
    Baseline trade - holds until signal replacement/reversal
    One active trade per (symbol, direction, webhook_source)
    """
    __tablename__ = "baseline_trades"

    id = Column(Integer, primary_key=True, index=True)

    # Trade identification
    symbol = Column(String(30), nullable=False)
    direction = Column(String(10), nullable=False)  # 'LONG' or 'SHORT'
    webhook_source = Column(String(50), nullable=False, index=True)

    # Entry
    entry_price = Column(Numeric(20, 8), nullable=False)
    entry_timestamp = Column(DateTime, nullable=False)

    # Live tracking
    current_price = Column(Numeric(20, 8))
    last_price_update = Column(DateTime)
    max_profit_pct = Column(Numeric(10, 4), default=0)
    max_drawdown_pct = Column(Numeric(10, 4), default=0)

    # Exit
    exit_price = Column(Numeric(20, 8))
    exit_timestamp = Column(DateTime)
    exit_reason = Column(String(30))  # 'replacement', 'reversal', 'manual'
    final_pnl_pct = Column(Numeric(10, 4))
    duration_minutes = Column(Integer)

    # Status
    status = Column(String(20), default='active', index=True)  # 'active', 'completed'

    # Metadata
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    milestones = relationship("BaselineMilestone", back_populates="trade", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index('idx_baseline_active', 'status', 'symbol', 'webhook_source'),
        Index('idx_baseline_entry_time', 'entry_timestamp'),
        # Unique constraint already created in raw SQL with WHERE clause
        # SQLAlchemy ORM doesn't need to recreate partial indexes
    )


class BaselineMilestone(Base):
    """
    Price milestones reached during baseline trade
    """
    __tablename__ = "baseline_milestones"

    id = Column(Integer, primary_key=True, index=True)
    baseline_trade_id = Column(Integer, ForeignKey('baseline_trades.id', ondelete='CASCADE'), nullable=False)

    # Milestone data
    milestone_type = Column(String(30), nullable=False, index=True)  # '+1pct', '+2pct', '-3pct'
    milestone_value = Column(Numeric(10, 4), nullable=False)
    hit_at = Column(DateTime, nullable=False)
    hit_price = Column(Numeric(20, 8), nullable=False)
    time_to_hit_minutes = Column(Integer)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    trade = relationship("BaselineTrade", back_populates="milestones")

    # Indexes
    __table_args__ = (
        Index('idx_baseline_milestone_trade', 'baseline_trade_id'),
        # Unique: one milestone type per trade
        UniqueConstraint('baseline_trade_id', 'milestone_type', name='uq_baseline_milestone'),
    )


class BaselineStatsDaily(Base):
    """
    Daily aggregated statistics per webhook source
    """
    __tablename__ = "baseline_stats_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False)
    webhook_source = Column(String(50), nullable=False)

    # Daily metrics
    trades_opened = Column(Integer, default=0)
    trades_closed = Column(Integer, default=0)
    avg_duration_minutes = Column(Numeric(10, 2))
    avg_final_pnl_pct = Column(Numeric(10, 4))
    max_profit_reached = Column(Numeric(10, 4))
    max_drawdown_reached = Column(Numeric(10, 4))

    # Exit reason breakdown
    exits_by_replacement = Column(Integer, default=0)
    exits_by_reversal = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())

    # Indexes
    __table_args__ = (
        UniqueConstraint('date', 'webhook_source', name='uq_baseline_daily_stats'),
    )
