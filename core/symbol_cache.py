"""
Кэш доступных торговых символов с автоматическим обновлением.
Основано на паттернах из Freqtrade.
"""
import time
import logging
from collections import Counter
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SymbolCache:
    """
    Кэширует список доступных символов с периодическим обновлением.

    Features:
    - O(1) проверка валидности символа
    - Автоматическое обновление раз в час
    - Принудительное обновление при большом количестве bad symbols
    - Thread-safe операции

    Based on: Freqtrade exchange/exchange.py validate_pairs()
    """

    def __init__(
        self,
        exchange_manager,
        refresh_interval: int = 3600,
        bad_symbol_threshold: int = 5
    ):
        """
        Args:
            exchange_manager: Менеджер биржи для получения markets
            refresh_interval: Интервал обновления кэша в секундах (default: 1 час)
            bad_symbol_threshold: Количество bad symbols для принудительного обновления
        """
        self.exchange_manager = exchange_manager
        self._cache: Dict[str, dict] = {}
        self._last_refresh: Optional[float] = None
        self._refresh_interval = refresh_interval
        self._bad_symbol_counter = Counter()
        self._bad_symbol_threshold = bad_symbol_threshold

        # Инициализация кэша при создании
        self._refresh()

    def is_valid(self, symbol: str) -> bool:
        """
        Проверяет существование и активность символа.

        Args:
            symbol: Торговый символ (например, 'BTC/USDT')

        Returns:
            bool: True если символ валидный и активный

        Example:
            >>> cache = SymbolCache(exchange_manager)
            >>> cache.is_valid('BTC/USDT')
            True
            >>> cache.is_valid('INVALID/USDT')
            False
        """
        # Проверяем нужно ли обновить кэш по времени
        if self._should_refresh():
            logger.info("Scheduled cache refresh triggered")
            self._refresh()

        # Если накопилось много bad symbols - принудительное обновление
        if self._bad_symbol_counter.total() >= self._bad_symbol_threshold:
            logger.warning(
                f"Detected {self._bad_symbol_counter.total()} invalid symbols, "
                f"forcing cache refresh"
            )
            self.force_refresh()

        # Проверяем наличие в кэше
        is_valid = symbol in self._cache

        if not is_valid:
            self._bad_symbol_counter[symbol] += 1
            logger.warning(
                f"Symbol {symbol} not found in cache "
                f"(attempt #{self._bad_symbol_counter[symbol]})"
            )

        return is_valid

    def _should_refresh(self) -> bool:
        """Проверяет нужно ли обновить кэш по времени"""
        if not self._last_refresh:
            return True

        elapsed = time.time() - self._last_refresh
        return elapsed > self._refresh_interval

    def _refresh(self):
        """
        Обновляет кэш символов с биржи.

        Based on: Freqtrade exchange.load_markets()
        """
        try:
            logger.info("Refreshing symbol cache from exchange")

            # Получаем markets с биржи (с reload=True для принудительного обновления)
            markets = self.exchange_manager.get_markets(reload=True)

            if not markets:
                logger.error("Received empty markets from exchange, keeping old cache")
                return

            # Сохраняем только активные символы
            self._cache = {
                symbol: market
                for symbol, market in markets.items()
                if market.get('active', True)
            }

            self._last_refresh = time.time()

            logger.info(
                f"Symbol cache refreshed: {len(self._cache)} active symbols available"
            )

        except Exception as e:
            logger.error(
                f"Failed to refresh symbol cache: {e}. Using stale cache.",
                exc_info=True
            )
            # Не падаем - используем старый кэш

    def force_refresh(self):
        """
        Принудительное обновление кэша (используется при большом количестве bad symbols).
        """
        logger.info("Forcing symbol cache refresh")
        self._bad_symbol_counter.clear()
        self._refresh()

    def get_cached_symbols(self) -> list:
        """
        Возвращает список всех кэшированных символов.

        Returns:
            list: Список символов в кэше
        """
        return list(self._cache.keys())

    def get_cache_age(self) -> Optional[float]:
        """
        Возвращает время в секундах с последнего обновления.

        Returns:
            float: Секунды с обновления или None если кэш не обновлялся
        """
        if not self._last_refresh:
            return None
        return time.time() - self._last_refresh