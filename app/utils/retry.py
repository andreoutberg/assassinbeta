"""
Retry decorator with exponential backoff for database operations

Handles transient database errors like connection timeouts, deadlocks, etc.
"""
import asyncio
import functools
import logging
from typing import Callable, TypeVar, Any
from sqlalchemy.exc import (
    OperationalError, 
    DBAPIError, 
    DatabaseError,
    IntegrityError
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


def async_retry(
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (OperationalError, DBAPIError, DatabaseError)
):
    """
    Retry decorator for async functions with exponential backoff
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 0.5)
        max_delay: Maximum delay between retries (default: 10.0)
        exponential_base: Base for exponential backoff calculation (default: 2.0)
        exceptions: Tuple of exception types to catch and retry (default: DB errors)
    
    Example:
        @async_retry(max_attempts=5, initial_delay=1.0)
        async def fetch_data(db: AsyncSession):
            result = await db.execute(query)
            return result.scalars().all()
    
    Retry delays follow exponential backoff:
    - Attempt 1: initial_delay * (exponential_base ^ 0) = 0.5s
    - Attempt 2: initial_delay * (exponential_base ^ 1) = 1.0s
    - Attempt 3: initial_delay * (exponential_base ^ 2) = 2.0s
    - Attempt 4: initial_delay * (exponential_base ^ 3) = 4.0s
    - etc., capped at max_delay
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    result = await func(*args, **kwargs)
                    
                    # Log success on retry (not on first attempt)
                    if attempt > 1:
                        logger.info(
                            f"✅ {func.__name__} succeeded on attempt {attempt}/{max_attempts}"
                        )
                    
                    return result
                    
                except exceptions as e:
                    last_exception = e
                    
                    # Don't retry on IntegrityError (unique constraint violations)
                    if isinstance(e, IntegrityError):
                        logger.error(f"IntegrityError in {func.__name__} - not retrying: {e}")
                        raise
                    
                    if attempt < max_attempts:
                        # Calculate delay with exponential backoff
                        delay = min(
                            initial_delay * (exponential_base ** (attempt - 1)),
                            max_delay
                        )
                        
                        logger.warning(
                            f"⚠️ {func.__name__} failed on attempt {attempt}/{max_attempts}: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                
                except Exception as e:
                    # Non-retryable exceptions (re-raise immediately)
                    logger.error(
                        f"Non-retryable error in {func.__name__}: {e}",
                        exc_info=True
                    )
                    raise
            
            # All retries exhausted
            from app.utils.exceptions import DatabaseOperationError
            raise DatabaseOperationError(
                func.__name__,
                f"Failed after {max_attempts} attempts. Last error: {last_exception}"
            )
        
        return wrapper
    return decorator


def sync_retry(
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (OperationalError, DBAPIError, DatabaseError)
):
    """
    Retry decorator for synchronous functions with exponential backoff
    
    Args: Same as async_retry
    
    Example:
        @sync_retry(max_attempts=5)
        def calculate_metrics(data):
            # Some computation that might fail transiently
            return process(data)
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    
                    if attempt > 1:
                        logger.info(
                            f"✅ {func.__name__} succeeded on attempt {attempt}/{max_attempts}"
                        )
                    
                    return result
                    
                except exceptions as e:
                    last_exception = e
                    
                    if isinstance(e, IntegrityError):
                        logger.error(f"IntegrityError in {func.__name__} - not retrying: {e}")
                        raise
                    
                    if attempt < max_attempts:
                        delay = min(
                            initial_delay * (exponential_base ** (attempt - 1)),
                            max_delay
                        )
                        
                        logger.warning(
                            f"⚠️ {func.__name__} failed on attempt {attempt}/{max_attempts}: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        
                        import time
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                
                except Exception as e:
                    logger.error(
                        f"Non-retryable error in {func.__name__}: {e}",
                        exc_info=True
                    )
                    raise
            
            from app.utils.exceptions import DatabaseOperationError
            raise DatabaseOperationError(
                func.__name__,
                f"Failed after {max_attempts} attempts. Last error: {last_exception}"
            )
        
        return wrapper
    return decorator


# Convenience decorators with common configurations
db_retry = async_retry(max_attempts=3, initial_delay=0.5)
aggressive_retry = async_retry(max_attempts=5, initial_delay=1.0, max_delay=30.0)
