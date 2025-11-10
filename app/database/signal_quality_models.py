"""
Enhanced Signal Quality Database Models

Tracks signal quality metrics to validate edge before optimization.
Includes high-WR potential prediction and consistency tracking.
"""

from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Index
from sqlalchemy.sql import func
from app.database.database import Base


class SignalQuality(Base):
    """
    Enhanced signal quality tracking table.

    Stores analysis of whether trading signals have predictive edge,
    with advanced metrics for high-WR potential detection.
    """

    __tablename__ = 'signal_quality'

    id = Column(Integer, primary_key=True, index=True)

    # Signal identification
    symbol = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False)  # LONG or SHORT
    webhook_source = Column(String(100), nullable=False)

    # Performance metrics
    raw_win_rate = Column(Numeric(5, 2))  # Win rate without TP/SL
    ci_lower = Column(Numeric(5, 2))  # 95% confidence interval lower bound
    ci_upper = Column(Numeric(5, 2))  # 95% confidence interval upper bound
    expected_value = Column(Numeric(10, 4))  # EV per trade

    # Statistical validation
    sample_size = Column(Integer)  # Number of baseline trades analyzed
    is_significant = Column(Boolean, default=False)  # p < 0.05
    p_value = Column(Numeric(10, 8))  # Binomial test p-value

    # Quality assessment
    has_edge = Column(Boolean, default=False, index=True)  # True if meets thresholds
    quality_score = Column(Numeric(5, 2))  # 0-100 composite score
    recommendation = Column(String(50))  # Enhanced recommendations

    # High-WR potential metrics (NEW)
    high_wr_potential = Column(Boolean, default=False, index=True)  # Predicted >70% Phase II
    phase2_predicted_wr = Column(Numeric(5, 2), default=0)  # Predicted Phase II win rate
    phase2_confidence = Column(Numeric(5, 2), default=0)  # Confidence in prediction (0-100)

    # Consistency tracking (NEW)
    consistency_score = Column(Numeric(5, 2), default=0)  # 0-100 stability score
    rolling_variance = Column(Numeric(10, 4), default=0)  # Variance in rolling win rates
    max_streak = Column(Integer, default=0)  # Maximum win streak observed
    current_streak = Column(Integer, default=0)  # Current win/loss streak

    # Early detection (NEW)
    early_detection_status = Column(String(30))  # exceptional, promising, poor, monitoring

    # Metadata
    last_analyzed_at = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())

    # Composite indexes for quick lookups
    __table_args__ = (
        Index('ix_signal_combo', 'symbol', 'direction', 'webhook_source', unique=True),
        Index('ix_has_edge', 'has_edge'),
        Index('ix_quality_score', 'quality_score'),
        Index('ix_high_wr_potential', 'high_wr_potential'),  # NEW index
        Index('ix_consistency_score', 'consistency_score'),  # NEW index
    )

    def __repr__(self):
        return (
            f"<SignalQuality(symbol={self.symbol}, direction={self.direction}, "
            f"source={self.webhook_source}, WR={self.raw_win_rate}%, "
            f"edge={self.has_edge}, score={self.quality_score}, "
            f"high_wr={self.high_wr_potential}, consistency={self.consistency_score})>"
        )