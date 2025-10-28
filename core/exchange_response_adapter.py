"""
Exchange Response Adapter - нормализует ответы от разных бирж
Решает проблему несовместимости форматов ответов
"""
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NormalizedOrder:
    """Унифицированная структура ордера"""
    id: str
    status: str  # 'closed', 'open', 'canceled'
    side: str  # 'buy', 'sell'
    amount: float
    filled: float
    price: Optional[float]
    average: Optional[float]
    symbol: str
    type: str  # 'market', 'limit', 'stop'
    raw_data: Dict  # Оригинальные данные


class ExchangeResponseAdapter:
    """
    Адаптер для нормализации ответов от разных бирж

    Проблема: Bybit и Binance возвращают данные в разных форматах
    Решение: Единый интерфейс для всех бирж
    """

    @staticmethod
    def normalize_order(order_data: Any, exchange: str) -> NormalizedOrder:
        """
        Нормализует ответ о создании ордера

        Args:
            order_data: Сырой ответ от биржи (ccxt Order object или dict)
            exchange: Название биржи ('binance', 'bybit')

        Returns:
            NormalizedOrder с гарантированными полями
        """

        # Если это уже словарь (ccxt parsed response)
        if isinstance(order_data, dict):
            raw = order_data
        else:
            # Если это объект, пытаемся получить словарь
            raw = order_data.__dict__ if hasattr(order_data, '__dict__') else {}

        if exchange.lower() == 'bybit':
            return ExchangeResponseAdapter._normalize_bybit_order(raw)
        elif exchange.lower() == 'binance':
            return ExchangeResponseAdapter._normalize_binance_order(raw)
        else:
            return ExchangeResponseAdapter._normalize_generic_order(raw)

    @staticmethod
    def _normalize_bybit_order(data: Dict) -> NormalizedOrder:
        """
        Нормализация Bybit ответа

        Bybit особенности:
        - Может не возвращать side/amount в market orders
        - Status может быть в info.orderStatus
        - Filled amount в info.cumExecQty
        """
        info = data.get('info', {})

        # Извлекаем данные из разных мест
        order_id = data.get('id') or info.get('orderId') or info.get('orderLinkId')

        # Status mapping для Bybit
        status_map = {
            # Bybit API format (uppercase)
            'Filled': 'closed',
            'PartiallyFilled': 'open',
            'New': 'open',
            'Created': 'open',
            'Cancelled': 'canceled',
            'Rejected': 'canceled',

            # CCXT normalized format (lowercase)
            # CRITICAL FIX: CCXT returns lowercase statuses ('open', 'closed', 'canceled')
            # but status_map only had uppercase Bybit API formats
            # This caused 'open' → 'unknown' → order rejection
            'closed': 'closed',
            'open': 'open',
            'canceled': 'canceled',
        }
        raw_status = info.get('orderStatus') or data.get('status', '')

        # CRITICAL FIX: Bybit create_order returns None status (API v5 minimal response)
        # Bybit API v5 returns only orderId - all other fields are None
        # Market orders execute instantly → treat None/empty as filled
        if raw_status is None or raw_status == '':
            status = 'closed'
        else:
            status = status_map.get(raw_status) or data.get('status') or 'unknown'

        # Extract side from response
        side = data.get('side') or info.get('side', '').lower()

        # CRITICAL FIX: Fail-fast if side is missing
        # This should NEVER happen if fetch_order was called (FIX #1.1)
        # If it does happen, it indicates a serious issue that must not be silently ignored
        if not side or side == 'unknown':
            logger.critical(
                f"❌ CRITICAL: Bybit order missing required 'side' field!\n"
                f"  Order ID: {order_id}\n"
                f"  This indicates minimal response was used.\n"
                f"  fetch_order should have been called but may have failed.\n"
                f"  Cannot proceed with 'unknown' side - would cause incorrect rollback!"
            )
            raise ValueError(
                f"Order {order_id} missing 'side' field. "
                f"Minimal response detected - fetch_order likely failed or was not called. "
                f"Cannot create position with unknown side (would break rollback logic)."
            )

        # Amount может быть в qty или cumExecQty
        amount = (
            data.get('amount') or
            data.get('filled') or
            float(info.get('qty', 0)) or
            float(info.get('cumExecQty', 0))
        )

        filled = (
            data.get('filled') or
            float(info.get('cumExecQty', 0)) or
            amount  # Для market orders filled = amount
        )

        # Цена исполнения
        price = data.get('price') or float(info.get('price', 0) or 0)
        average = data.get('average') or float(info.get('avgPrice', 0) or 0)

        # Если нет average price но есть filled, считаем что исполнено по market
        if not average and filled > 0 and not price:
            average = float(info.get('lastExecPrice', 0))

        symbol = data.get('symbol') or info.get('symbol', '')
        order_type = (data.get('type') or 'market').lower()

        logger.debug(f"Bybit order normalized: id={order_id}, status={status}, filled={filled}/{amount}")

        return NormalizedOrder(
            id=order_id,
            status=status,
            side=side,
            amount=amount,
            filled=filled,
            price=price,
            average=average,
            symbol=symbol,
            type=order_type,
            raw_data=data
        )

    @staticmethod
    def _normalize_binance_order(data: Dict) -> NormalizedOrder:
        """
        Нормализация Binance ответа

        Binance обычно возвращает полные данные
        """
        info = data.get('info', {})

        order_id = data.get('id') or info.get('orderId')

        # Binance status mapping
        status_map = {
            'FILLED': 'closed',
            'PARTIALLY_FILLED': 'open',
            'NEW': 'open',
            'CANCELED': 'canceled',
            'REJECTED': 'canceled',
            'EXPIRED': 'canceled'
        }
        raw_status = info.get('status') or data.get('status', '')
        status = status_map.get(raw_status) or data.get('status') or 'unknown'

        side = data.get('side', '').lower()

        # CRITICAL FIX: Fail-fast if side is missing
        # This should NEVER happen if fetch_order was called (FIX #1.1)
        if not side:
            logger.critical(
                f"❌ CRITICAL: Binance order missing required 'side' field!\n"
                f"  Order ID: {order_id}\n"
                f"  Cannot proceed without side - would cause incorrect rollback!"
            )
            raise ValueError(
                f"Order {order_id} missing 'side' field. "
                f"Cannot create position with unknown side (would break rollback logic)."
            )

        amount = data.get('amount') or float(info.get('origQty', 0))
        filled = data.get('filled') or float(info.get('executedQty', 0))
        price = data.get('price') or float(info.get('price', 0))
        average = data.get('average') or float(info.get('avgPrice', 0))
        symbol = data.get('symbol') or info.get('symbol', '')
        order_type = (data.get('type') or 'market').lower()

        logger.debug(f"Binance order normalized: id={order_id}, status={status}, filled={filled}/{amount}")

        return NormalizedOrder(
            id=order_id,
            status=status,
            side=side,
            amount=amount,
            filled=filled,
            price=price,
            average=average,
            symbol=symbol,
            type=order_type,
            raw_data=data
        )

    @staticmethod
    def _normalize_generic_order(data: Dict) -> NormalizedOrder:
        """Fallback для других бирж"""
        return NormalizedOrder(
            id=data.get('id', 'unknown'),
            status=data.get('status', 'unknown'),
            side=data.get('side', 'unknown'),
            amount=data.get('amount', 0),
            filled=data.get('filled', 0),
            price=data.get('price'),
            average=data.get('average'),
            symbol=data.get('symbol', ''),
            type=data.get('type', 'unknown'),
            raw_data=data
        )

    @staticmethod
    def is_order_filled(order: NormalizedOrder) -> bool:
        """
        Проверяет, исполнен ли ордер полностью

        Учитывает особенности разных бирж:
        - Bybit market orders могут сразу иметь status='closed'
        - Binance требует filled >= amount
        """
        if order.status == 'closed':
            return True

        # Для market orders
        if order.type == 'market' and order.filled > 0:
            # Допускаем небольшую погрешность (0.1%)
            return order.filled >= order.amount * 0.999

        return False

    @staticmethod
    def extract_execution_price(order: NormalizedOrder) -> float:
        """
        Извлекает цену исполнения ордера

        Приоритет:
        1. average (средняя цена исполнения)
        2. price (для limit orders)
        3. из raw_data для особых случаев
        """
        if order.average and order.average > 0:
            return order.average

        if order.price and order.price > 0:
            return order.price

        # Fallback to raw data
        info = order.raw_data.get('info', {})

        # Попытки извлечь из разных полей
        possible_prices = [
            info.get('avgPrice'),
            info.get('lastExecPrice'),
            info.get('price'),
            order.raw_data.get('lastTradePrice')
        ]

        for price in possible_prices:
            if price:
                try:
                    p = float(price)
                    if p > 0:
                        return p
                except (ValueError, TypeError):
                    continue

        logger.warning(f"Could not extract execution price for order {order.id}")
        return 0.0