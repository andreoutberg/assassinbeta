"""
Pydantic schemas for demo trading endpoints
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime


class DemoPositionCreate(BaseModel):
    """Schema for creating a new demo position"""
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTCUSDT)")
    side: Literal["long", "short"] = Field(..., description="Position side")
    quantity: float = Field(..., gt=0, description="Position size")
    entry_price: Optional[float] = Field(None, gt=0, description="Entry price (uses market price if not provided)")
    leverage: int = Field(5, ge=1, le=100, description="Leverage")
    take_profit: Optional[float] = Field(None, gt=0, description="Take profit price")
    stop_loss: Optional[float] = Field(None, gt=0, description="Stop loss price")
    strategy_id: Optional[str] = Field(None, description="Associated strategy ID")
    signal_id: Optional[str] = Field(None, description="Associated signal ID")

    @validator('take_profit')
    def validate_take_profit(cls, v, values):
        if v and 'side' in values and 'entry_price' in values and values['entry_price']:
            if values['side'] == 'long' and v <= values['entry_price']:
                raise ValueError("Take profit must be higher than entry price for long positions")
            elif values['side'] == 'short' and v >= values['entry_price']:
                raise ValueError("Take profit must be lower than entry price for short positions")
        return v

    @validator('stop_loss')
    def validate_stop_loss(cls, v, values):
        if v and 'side' in values and 'entry_price' in values and values['entry_price']:
            if values['side'] == 'long' and v >= values['entry_price']:
                raise ValueError("Stop loss must be lower than entry price for long positions")
            elif values['side'] == 'short' and v <= values['entry_price']:
                raise ValueError("Stop loss must be higher than entry price for short positions")
        return v


class DemoPositionUpdate(BaseModel):
    """Schema for updating a demo position"""
    take_profit: Optional[float] = Field(None, gt=0, description="New take profit price")
    stop_loss: Optional[float] = Field(None, gt=0, description="New stop loss price")


class DemoPositionClose(BaseModel):
    """Schema for closing a demo position"""
    exit_price: Optional[float] = Field(None, gt=0, description="Exit price (uses market price if not provided)")
    reason: Optional[str] = Field(None, description="Close reason (manual, tp_hit, sl_hit, etc.)")


class DemoPositionResponse(BaseModel):
    """Response schema for demo position"""
    id: str
    symbol: str
    side: Literal["long", "short"]
    quantity: float
    entry_price: float
    exit_price: Optional[float]
    current_price: Optional[float]
    leverage: int
    take_profit: Optional[float]
    stop_loss: Optional[float]
    status: Literal["open", "closed", "cancelled"]
    unrealized_pnl: Optional[float]
    realized_pnl: Optional[float]
    commission: float
    strategy_id: Optional[str]
    signal_id: Optional[str]
    close_reason: Optional[str]
    created_at: datetime
    closed_at: Optional[datetime]

    class Config:
        orm_mode = True


class DemoBalanceResponse(BaseModel):
    """Response schema for demo account balance"""
    balance: float = Field(..., description="Account balance")
    equity: float = Field(..., description="Account equity (balance + unrealized P&L)")
    margin_used: float = Field(..., description="Margin currently in use")
    free_margin: float = Field(..., description="Available margin")
    unrealized_pnl: float = Field(..., description="Total unrealized P&L")
    margin_level: float = Field(..., description="Margin level percentage")
    open_positions: int = Field(..., description="Number of open positions")
    total_commission: float = Field(..., description="Total commission paid")


class DemoPositionStats(BaseModel):
    """Response schema for demo position statistics"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_profit: float
    total_loss: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    current_balance: float
    period: str