"""
Utility decorators for the trading system
"""
import asyncio
import functools
import logging
from typing import Callable, Any
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Retry decorator with exponential backoff

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier for each retry
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay

            while attempt < max_attempts:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise

                    logger.warning(f"{func.__name__} attempt {attempt} failed, retrying in {current_delay}s: {e}")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay

            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise

                    logger.warning(f"{func.__name__} attempt {attempt} failed, retrying in {current_delay}s")
                    time.sleep(current_delay)
                    current_delay *= backoff

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def rate_limit(calls: int, period: float):
    """
    Rate limiting decorator

    Args:
        calls: Number of calls allowed
        period: Time period in seconds
    """

    def decorator(func: Callable) -> Callable:
        # Store call times
        func._call_times = []
        func._lock = asyncio.Lock()

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            async with func._lock:
                now = time.time()

                # Remove old calls
                func._call_times = [t for t in func._call_times if now - t < period]

                # Check rate limit
                if len(func._call_times) >= calls:
                    sleep_time = period - (now - func._call_times[0])
                    if sleep_time > 0:
                        logger.debug(f"Rate limit reached for {func.__name__}, sleeping {sleep_time:.2f}s")
                        await asyncio.sleep(sleep_time)
                        # Recalculate after sleep
                        now = time.time()
                        func._call_times = [t for t in func._call_times if now - t < period]

                # Record call and execute
                func._call_times.append(now)
                return await func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            raise ValueError("rate_limit decorator only supports async functions")

    return decorator


def measure_time(func: Callable) -> Callable:
    """Measure execution time of function"""

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.debug(f"{func.__name__} took {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.error(f"{func.__name__} failed after {elapsed:.3f}s: {e}")
            raise

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.debug(f"{func.__name__} took {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.error(f"{func.__name__} failed after {elapsed:.3f}s: {e}")
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def cache_result(ttl: int = 60):
    """
    Cache function result for TTL seconds

    Args:
        ttl: Time to live in seconds
    """

    def decorator(func: Callable) -> Callable:
        func._cache = {}
        func._cache_time = {}

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Create cache key
            cache_key = str(args) + str(kwargs)

            # Check cache
            if cache_key in func._cache:
                if time.time() - func._cache_time[cache_key] < ttl:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return func._cache[cache_key]

            # Execute and cache
            result = await func(*args, **kwargs)
            func._cache[cache_key] = result
            func._cache_time[cache_key] = time.time()

            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            raise ValueError("cache_result decorator only supports async functions")

    return decorator


# Alias for backward compatibility
async_retry = retry