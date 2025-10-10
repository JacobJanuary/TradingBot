"""
Rate limiter with exponential backoff and jitter
Prevents API bans and handles rate limit exceptions gracefully
"""
import asyncio
import time
import random
import logging
import os
from typing import Dict, Optional, Any, Callable
from functools import wraps
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_second: int = 10
    requests_per_minute: int = 100
    burst_size: int = 20
    min_retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    max_retries: int = 5
    backoff_factor: float = 2.0
    jitter_factor: float = 0.1  # 10% jitter


@dataclass
class RateLimitStats:
    """Statistics for rate limiting"""
    total_requests: int = 0
    successful_requests: int = 0
    rate_limited_requests: int = 0
    failed_requests: int = 0
    total_wait_time: float = 0.0
    last_rate_limit: Optional[datetime] = None
    request_history: deque = field(default_factory=lambda: deque(maxlen=1000))


class RateLimiter:
    """
    Advanced rate limiter with exponential backoff and jitter
    """
    
    def __init__(self, config: RateLimitConfig):
        """
        Initialize rate limiter
        
        Args:
            config: Rate limiting configuration
        """
        self.config = config
        self.stats = RateLimitStats()
        
        # Token bucket for rate limiting
        self.tokens = config.burst_size
        self.max_tokens = config.burst_size
        self.last_refill = time.time()
        self.refill_rate = config.requests_per_second
        
        # Tracking for per-minute limits
        self.minute_requests = deque()
        
        # Backoff state
        self.current_delay = config.min_retry_delay
        self.consecutive_limits = 0
        
        # Lock for thread safety
        self.lock = asyncio.Lock()
    
    def _refill_tokens(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def _clean_minute_requests(self):
        """Remove requests older than 1 minute"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
        while self.minute_requests and self.minute_requests[0] < cutoff:
            self.minute_requests.popleft()
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate delay with exponential backoff and jitter
        
        Args:
            attempt: Current retry attempt
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff
        base_delay = min(
            self.config.min_retry_delay * (self.config.backoff_factor ** attempt),
            self.config.max_retry_delay
        )
        
        # Add jitter (±jitter_factor)
        jitter_range = base_delay * self.config.jitter_factor
        jitter = random.uniform(-jitter_range, jitter_range)
        
        delay = base_delay + jitter
        
        # Ensure minimum delay
        return max(self.config.min_retry_delay, delay)
    
    async def acquire(self) -> bool:
        """
        Acquire permission to make a request
        
        Returns:
            True if request can proceed, False if rate limited
        """
        async with self.lock:
            self._refill_tokens()
            self._clean_minute_requests()
            
            # Check per-minute limit
            if len(self.minute_requests) >= self.config.requests_per_minute:
                logger.warning(f"Per-minute rate limit reached: {len(self.minute_requests)}/{self.config.requests_per_minute}")
                self.stats.rate_limited_requests += 1
                self.stats.last_rate_limit = datetime.now(timezone.utc)
                return False
            
            # Check token bucket
            if self.tokens < 1:
                logger.warning(f"Token bucket exhausted: {self.tokens:.2f}/{self.max_tokens}")
                self.stats.rate_limited_requests += 1
                self.stats.last_rate_limit = datetime.now(timezone.utc)
                return False
            
            # Consume token
            self.tokens -= 1
            self.minute_requests.append(datetime.now(timezone.utc))
            self.stats.total_requests += 1
            self.stats.request_history.append(datetime.now(timezone.utc))
            
            # Reset consecutive limits on success
            self.consecutive_limits = 0
            self.current_delay = self.config.min_retry_delay
            
            return True
    
    async def wait_if_needed(self) -> float:
        """
        Wait if rate limited
        
        Returns:
            Time waited in seconds
        """
        if await self.acquire():
            return 0.0
        
        # Calculate backoff delay
        delay = self._calculate_backoff_delay(self.consecutive_limits)
        self.consecutive_limits += 1
        
        logger.info(f"Rate limited, waiting {delay:.2f}s (attempt {self.consecutive_limits})")
        
        # Wait with progress logging for long delays
        if delay > 10:
            intervals = int(delay / 10)
            for i in range(intervals):
                await asyncio.sleep(10)
                remaining = delay - (i + 1) * 10
                if remaining > 0:
                    logger.debug(f"Waiting... {remaining:.0f}s remaining")
            await asyncio.sleep(delay % 10)
        else:
            await asyncio.sleep(delay)
        
        self.stats.total_wait_time += delay
        return delay
    
    async def execute_with_retry(self, 
                                 func: Callable, 
                                 *args, 
                                 **kwargs) -> Any:
        """
        Execute function with automatic retry on rate limit
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If max retries exceeded
        """
        import ccxt
        
        last_exception = None
        
        for attempt in range(self.config.max_retries):
            try:
                # Wait for rate limit if needed
                wait_time = await self.wait_if_needed()
                if wait_time > 0:
                    logger.debug(f"Waited {wait_time:.2f}s before attempt {attempt + 1}")
                
                # Execute function
                result = await func(*args, **kwargs)
                self.stats.successful_requests += 1
                return result
                
            except ccxt.RateLimitExceeded as e:
                last_exception = e
                self.stats.rate_limited_requests += 1
                self.consecutive_limits += 1
                
                if attempt < self.config.max_retries - 1:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        f"Rate limit exceeded on attempt {attempt + 1}/{self.config.max_retries}, "
                        f"waiting {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Max retries exceeded for rate limit: {e}")
                    
            except ccxt.NetworkError as e:
                last_exception = e

                if attempt < self.config.max_retries - 1:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        f"Network error on attempt {attempt + 1}/{self.config.max_retries}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Max retries exceeded for network error: {e}")

            except ccxt.OrderNotFound as e:
                # OrderNotFound is expected behavior (order filled/cancelled/expired)
                # Not an error - log as INFO and re-raise without stats increment
                logger.info(f"Order not found (likely filled/cancelled): {e}")
                raise

            except Exception as e:
                self.stats.failed_requests += 1
                logger.error(f"Unexpected error in rate limited function: {e}")
                raise
        
        self.stats.failed_requests += 1
        raise last_exception or Exception("Max retries exceeded")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics"""
        return {
            'total_requests': self.stats.total_requests,
            'successful_requests': self.stats.successful_requests,
            'rate_limited_requests': self.stats.rate_limited_requests,
            'failed_requests': self.stats.failed_requests,
            'total_wait_time': round(self.stats.total_wait_time, 2),
            'last_rate_limit': self.stats.last_rate_limit.isoformat() if self.stats.last_rate_limit else None,
            'current_tokens': round(self.tokens, 2),
            'consecutive_limits': self.consecutive_limits,
            'requests_last_minute': len(self.minute_requests)
        }
    
    def reset_backoff(self):
        """Reset backoff state"""
        self.consecutive_limits = 0
        self.current_delay = self.config.min_retry_delay


class ExchangeRateLimiter:
    """
    Rate limiter specifically for exchange operations
    """
    
    # Exchange-specific configurations (loaded from environment variables)
    EXCHANGE_CONFIGS = {
        'binance': RateLimitConfig(
            requests_per_second=int(os.getenv('BINANCE_RATE_LIMIT_PER_SEC', 16)),
            requests_per_minute=int(os.getenv('BINANCE_RATE_LIMIT_PER_MIN', 960)),
            burst_size=50,
            min_retry_delay=1.0,
            max_retry_delay=60.0,
            max_retries=5
        ),
        'bybit': RateLimitConfig(
            requests_per_second=int(os.getenv('BYBIT_RATE_LIMIT_PER_SEC', 8)),
            requests_per_minute=int(os.getenv('BYBIT_RATE_LIMIT_PER_MIN', 96)),
            burst_size=20,
            min_retry_delay=2.0,
            max_retry_delay=120.0,
            max_retries=3
        ),
        'default': RateLimitConfig(
            requests_per_second=int(os.getenv('DEFAULT_RATE_LIMIT_PER_SEC', 5)),
            requests_per_minute=int(os.getenv('DEFAULT_RATE_LIMIT_PER_MIN', 60)),
            burst_size=10,
            min_retry_delay=2.0,
            max_retry_delay=60.0,
            max_retries=3
        )
    }
    
    def __init__(self, exchange_name: str):
        """
        Initialize exchange rate limiter
        
        Args:
            exchange_name: Name of the exchange
        """
        self.exchange_name = exchange_name.lower()
        config = self.EXCHANGE_CONFIGS.get(
            self.exchange_name, 
            self.EXCHANGE_CONFIGS['default']
        )
        self.limiter = RateLimiter(config)
        
        logger.info(
            f"Rate limiter initialized for {exchange_name}: "
            f"{config.requests_per_second} req/s, "
            f"{config.requests_per_minute} req/min"
        )
    
    async def execute_request(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute exchange request with rate limiting
        
        Args:
            func: Exchange API function
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            API response
        """
        return await self.limiter.execute_with_retry(func, *args, **kwargs)
    
    def rate_limit_decorator(self):
        """
        Decorator for rate limiting functions
        
        Usage:
            @rate_limiter.rate_limit_decorator()
            async def fetch_balance(self):
                return await self.exchange.fetch_balance()
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await self.limiter.execute_with_retry(func, *args, **kwargs)
            return wrapper
        return decorator


# Global rate limiter instances per exchange
_rate_limiters: Dict[str, ExchangeRateLimiter] = {}


def get_rate_limiter(exchange_name: str) -> ExchangeRateLimiter:
    """
    Get or create rate limiter for exchange
    
    Args:
        exchange_name: Name of the exchange
        
    Returns:
        ExchangeRateLimiter instance
    """
    if exchange_name not in _rate_limiters:
        _rate_limiters[exchange_name] = ExchangeRateLimiter(exchange_name)
    return _rate_limiters[exchange_name]