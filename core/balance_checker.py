"""
Balance Checker - проверка доступных средств перед открытием позиций
"""
import logging
import decimal
from typing import Dict, Optional
from decimal import Decimal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class BalanceChecker:
    """
    Проверяет наличие достаточных средств на биржах перед открытием позиций
    
    Features:
    - Кэширование балансов (обновление каждые 10 секунд)
    - Разделение по биржам
    - Резервирование средств для открытых позиций
    - Минимальный баланс = размер позиции
    """
    
    def __init__(self, exchanges: Dict, position_size_usd: float):
        """
        Args:
            exchanges: Dict[exchange_name, ExchangeManager]
            position_size_usd: Размер позиции в USD (из конфига)
        """
        self.exchanges = exchanges
        self.position_size_usd = Decimal(str(position_size_usd))
        
        # Кэш балансов по биржам
        self._balance_cache = {}  # {exchange_name: {'balance': Decimal, 'updated_at': datetime}}
        self._cache_ttl_seconds = 10  # Обновлять каждые 10 секунд
        
        # Tracking недостаточных средств
        self._insufficient_funds_by_exchange = {}  # {exchange_name: last_warning_time}
        self._warning_cooldown_seconds = 60  # Предупреждение раз в минуту
        
        logger.info(
            f"BalanceChecker initialized: "
            f"position_size={self.position_size_usd} USD, "
            f"cache_ttl={self._cache_ttl_seconds}s"
        )
    
    async def has_sufficient_balance(
        self,
        exchange_name: str,
        required_usd: Optional[Decimal] = None
    ) -> bool:
        """
        Проверяет наличие достаточного баланса на бирже
        
        Args:
            exchange_name: Имя биржи ('binance', 'bybit')
            required_usd: Требуемая сумма в USD (если None, использует position_size_usd)
            
        Returns:
            bool: True если средств достаточно, False если нет
        """
        try:
            required = required_usd or self.position_size_usd
            
            # Получаем баланс (из кэша или обновляем)
            available_balance = await self._get_available_balance(exchange_name)
            
            if available_balance is None:
                logger.error(f"Could not fetch balance for {exchange_name}")
                return False
            
            # Проверяем достаточность средств
            has_funds = available_balance >= required
            
            if not has_funds:
                self._log_insufficient_funds(exchange_name, available_balance, required)
            
            return has_funds
            
        except Exception as e:
            logger.error(f"Error checking balance for {exchange_name}: {e}", exc_info=True)
            return False
    
    async def _get_available_balance(self, exchange_name: str) -> Optional[Decimal]:
        """
        Получает доступный баланс USDT на бирже (с кэшированием)
        
        Returns:
            Decimal: Доступный баланс в USDT или None при ошибке
        """
        now = datetime.now()
        
        # Проверяем кэш
        if exchange_name in self._balance_cache:
            cache_entry = self._balance_cache[exchange_name]
            age = (now - cache_entry['updated_at']).total_seconds()
            
            if age < self._cache_ttl_seconds:
                # Кэш актуален
                logger.debug(
                    f"Using cached balance for {exchange_name}: "
                    f"{cache_entry['balance']} USDT (age: {age:.1f}s)"
                )
                return cache_entry['balance']
        
        # Кэш устарел или отсутствует - обновляем
        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                logger.error(f"Exchange {exchange_name} not found")
                return None
            
            # Получаем баланс
            balance_data = await exchange.fetch_balance()
            
            # Извлекаем доступный баланс USDT
            available = None
            
            # Для Bybit Unified Account: free['USDT'] может быть None
            # Используем total['USDT'] как доступный баланс (минус used)
            if exchange_name == 'bybit':
                # Bybit Unified Account format
                usdt_data = balance_data.get('USDT', {})
                free_balance = usdt_data.get('free')
                total_balance = usdt_data.get('total', 0)
                used_balance = usdt_data.get('used', 0)
                
                # ✅ FIX: Validate values before Decimal conversion to prevent ConversionSyntax
                if free_balance is not None and free_balance > 0:
                    # Если free доступен, используем его
                    try:
                        available = Decimal(str(free_balance))
                    except (ValueError, decimal.InvalidOperation) as e:
                        logger.warning(f"Invalid free_balance value: {free_balance}, using 0")
                        available = Decimal('0')
                else:
                    # Иначе вычисляем: total - used
                    # Ensure both values are valid before conversion
                    try:
                        total = Decimal(str(total_balance)) if total_balance is not None else Decimal('0')
                        used = Decimal(str(used_balance)) if used_balance is not None else Decimal('0')
                        available = total - used
                    except (ValueError, decimal.InvalidOperation) as e:
                        logger.warning(f"Invalid balance values: total={total_balance}, used={used_balance}, using 0")
                        available = Decimal('0')
                
                logger.debug(
                    f"Bybit balance: total={total_balance}, used={used_balance}, "
                    f"free={free_balance}, calculated_available={available}"
                )
            else:
                # Binance и другие: используем standard format
                usdt_balance = balance_data.get('free', {}).get('USDT', 0)
                available = Decimal(str(usdt_balance))
                logger.debug(f"Balance for {exchange_name}: free={available}")
            
            # Обновляем кэш
            self._balance_cache[exchange_name] = {
                'balance': available,
                'updated_at': now
            }
            
            logger.debug(
                f"✅ Updated balance for {exchange_name}: {available} USDT"
            )
            
            return available
            
        except Exception as e:
            logger.error(f"Failed to fetch balance for {exchange_name}: {e}", exc_info=True)
            return None
    
    def _log_insufficient_funds(
        self,
        exchange_name: str,
        available: Decimal,
        required: Decimal
    ):
        """
        Логирует предупреждение о недостаточных средствах (с rate limiting)
        """
        now = datetime.now()
        
        # Проверяем когда последний раз предупреждали
        last_warning = self._insufficient_funds_by_exchange.get(exchange_name)
        
        if last_warning:
            time_since_warning = (now - last_warning).total_seconds()
            if time_since_warning < self._warning_cooldown_seconds:
                # Слишком рано для повторного предупреждения
                logger.debug(
                    f"Insufficient funds on {exchange_name} "
                    f"(available: {available}, required: {required}) - warning suppressed"
                )
                return
        
        # Логируем предупреждение
        deficit = required - available
        logger.warning(
            f"💰 INSUFFICIENT FUNDS on {exchange_name}:\n"
            f"   Available: {available:.2f} USDT\n"
            f"   Required:  {required:.2f} USDT\n"
            f"   Deficit:   {deficit:.2f} USDT\n"
            f"   ⏸️ Skipping signals for {exchange_name} until funds available"
        )
        
        # Обновляем время последнего предупреждения
        self._insufficient_funds_by_exchange[exchange_name] = now
    
    async def get_balance_summary(self) -> Dict[str, Decimal]:
        """
        Получает сводку балансов по всем биржам
        
        Returns:
            Dict[exchange_name, available_balance_usdt]
        """
        summary = {}
        
        for exchange_name in self.exchanges.keys():
            balance = await self._get_available_balance(exchange_name)
            if balance is not None:
                summary[exchange_name] = balance
        
        return summary
    
    def invalidate_cache(self, exchange_name: Optional[str] = None):
        """
        Инвалидирует кэш балансов
        
        Args:
            exchange_name: Имя биржи (если None, инвалидирует все)
        """
        if exchange_name:
            if exchange_name in self._balance_cache:
                del self._balance_cache[exchange_name]
                logger.debug(f"Invalidated balance cache for {exchange_name}")
        else:
            self._balance_cache.clear()
            logger.debug("Invalidated all balance caches")
