"""
Core Trading Models

Defines the main trade setup and milestone tracking models.
"""
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base


class TradeSetup(Base):
    """
    Main trade setup record

    Tracks all trades from entry to exit across all phases.
    """
    __tablename__ = "trade_setups"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # 'long' or 'short'
    webhook_source = Column(String(100), nullable=False, index=True)
    risk_strategy = Column(String(50), nullable=False, index=True)  # 'baseline', 'strategy_A', etc.

    # Entry data
    entry_price = Column(Numeric(20, 8), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    position_size = Column(Numeric(20, 8))

    # Exit data (filled when trade completes)
    exit_price = Column(Numeric(20, 8))
    exit_time = Column(DateTime(timezone=True))
    exit_reason = Column(String(50))  # 'tp1', 'tp2', 'tp3', 'sl', 'time_exit', 'opposite_signal'

    # P&L
    final_pnl_pct = Column(Numeric(10, 4))
    final_pnl_usd = Column(Numeric(10, 2))

    # Trade parameters
    tp1_pct = Column(Numeric(10, 4))
    tp2_pct = Column(Numeric(10, 4))
    tp3_pct = Column(Numeric(10, 4))
    sl_pct = Column(Numeric(10, 4))
    trailing_enabled = Column(Boolean, default=False)
    trailing_activation = Column(Numeric(10, 4))
    trailing_distance = Column(Numeric(10, 4))
    breakeven_trigger_pct = Column(Numeric(10, 4))

    # Status tracking
    status = Column(String(20), nullable=False, index=True)  # 'active', 'completed', 'cancelled'
    completed_at = Column(DateTime(timezone=True))

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    milestones = relationship("TradeMilestones", back_populates="trade", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TradeSetup {self.id} {self.symbol} {self.direction} {self.risk_strategy}>"


class TradeMilestones(Base):
    """
    Real-time milestone tracking for trades

    Records max profit, max drawdown, and price movements for simulation accuracy.
    """
    __tablename__ = "trade_milestones"

    id = Column(Integer, primary_key=True)
    trade_setup_id = Column(Integer, ForeignKey('trade_setups.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Price milestones
    max_profit_price = Column(Numeric(20, 8))
    max_profit_pct = Column(Numeric(10, 4))
    max_profit_time = Column(DateTime(timezone=True))

    max_drawdown_price = Column(Numeric(20, 8))
    max_drawdown_pct = Column(Numeric(10, 4))
    max_drawdown_time = Column(DateTime(timezone=True))

    # Milestone data (chronological price points for simulation)
    milestone_data = Column(Text)  # JSON string of [{timestamp, price, pnl_pct}, ...]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    trade = relationship("TradeSetup", back_populates="milestones")

    def __repr__(self):
        return f"<TradeMilestones trade={self.trade_setup_id} max_profit={self.max_profit_pct}%>"
