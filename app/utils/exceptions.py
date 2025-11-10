"""
Custom exceptions for the Andre Assassin trading system

These exceptions provide better error handling and debugging compared to returning None/[]
"""


class StrategyError(Exception):
    """Base exception for strategy-related errors"""
    pass


class InsufficientDataError(StrategyError):
    """Raised when insufficient baseline data exists to generate strategies"""
    def __init__(self, symbol: str, direction: str, required: int, actual: int):
        self.symbol = symbol
        self.direction = direction
        self.required = required
        self.actual = actual
        super().__init__(
            f"Insufficient data for {symbol} {direction}: "
            f"need {required} baseline trades, have {actual}"
        )


class InvalidTradeDataError(StrategyError):
    """Raised when trade data is invalid or incomplete"""
    def __init__(self, trade_id: int, reason: str):
        self.trade_id = trade_id
        self.reason = reason
        super().__init__(f"Invalid trade data for trade {trade_id}: {reason}")


class NoEligibleStrategyError(StrategyError):
    """Raised when no strategy meets Phase III eligibility criteria"""
    def __init__(self, symbol: str, direction: str):
        self.symbol = symbol
        self.direction = direction
        super().__init__(
            f"No eligible strategies for {symbol} {direction} - "
            f"all strategies failed Phase III requirements"
        )


class StrategyGenerationError(StrategyError):
    """Raised when strategy generation fails"""
    def __init__(self, symbol: str, direction: str, reason: str):
        self.symbol = symbol
        self.direction = direction
        self.reason = reason
        super().__init__(
            f"Failed to generate strategies for {symbol} {direction}: {reason}"
        )


class SimulationError(StrategyError):
    """Raised when strategy simulation fails"""
    def __init__(self, trade_id: int, strategy_name: str, reason: str):
        self.trade_id = trade_id
        self.strategy_name = strategy_name
        self.reason = reason
        super().__init__(
            f"Simulation failed for trade {trade_id} with {strategy_name}: {reason}"
        )


class DatabaseOperationError(Exception):
    """Raised when database operations fail after retries"""
    def __init__(self, operation: str, reason: str):
        self.operation = operation
        self.reason = reason
        super().__init__(f"Database operation '{operation}' failed: {reason}")


class ValidationError(Exception):
    """Raised when data validation fails"""
    def __init__(self, field: str, value, reason: str):
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"Validation failed for {field}={value}: {reason}")
