"""
Pydantic schemas for signals endpoints
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
from datetime import datetime


class SignalGenerateRequest(BaseModel):
    """Request schema for generating a signal"""
    symbol: str = Field(..., description="Trading pair symbol")
    timeframe: str = Field("15m", description="Timeframe for analysis")
    strategy_id: Optional[str] = Field(None, description="Specific strategy to use")
    force: bool = Field(False, description="Force signal generation even if conditions are suboptimal")


class SignalExecuteRequest(BaseModel):
    """Request schema for executing a signal"""
    quantity: float = Field(..., gt=0, description="Position size")
    leverage: int = Field(5, ge=1, le=100, description="Leverage to use")


class SignalResponse(BaseModel):
    """Response schema for signal data"""
    id: str
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry_price: float
    take_profit: float
    stop_loss: float
    confidence: float = Field(..., ge=0, le=1)
    timeframe: str
    strategy_name: str
    indicators: Dict[str, Any]
    timestamp: datetime
    is_active: bool
    risk_reward_ratio: float

    class Config:
        orm_mode = True


class SignalQualityResponse(BaseModel):
    """Response schema for signal quality metrics"""
    total_signals: int
    win_rate: float
    accuracy: float
    avg_confidence: float
    avg_pnl: float
    avg_risk_reward: float
    quality_distribution: Dict[str, int]
    period: str
    symbol: Optional[str]