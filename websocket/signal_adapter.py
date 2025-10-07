"""
Signal Adapter для преобразования WebSocket сигналов в формат бота
"""
import logging
from typing import Dict, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SignalAdapter:
    """
    Адаптер для преобразования WebSocket сигналов в формат, ожидаемый ботом
    
    WebSocket формат:
    {
        "id": 12345,
        "pair_symbol": "BTCUSDT",
        "recommended_action": "BUY",
        "score_week": 75.5,
        "score_month": 68.2,
        "timestamp": "2025-10-06T14:20:00",
        "created_at": "2025-10-06T14:20:05",
        "trading_pair_id": 1234
    }
    
    Формат бота:
    {
        "id": int,
        "symbol": str,
        "action": str,
        "score_week": float,
        "score_month": float,
        "created_at": datetime,
        "exchange": str,
        "wave_timestamp": datetime
    }
    """
    
    def __init__(self, trading_pair_mapping: Dict[int, str] = None):
        """
        Args:
            trading_pair_mapping: Маппинг trading_pair_id -> exchange_name
                                 Если None, попробует определить из символа
        """
        self.trading_pair_mapping = trading_pair_mapping or {}
        
        # Fallback маппинг: если trading_pair_id неизвестен,
        # используем простую эвристику по суффиксу символа
        self.exchange_fallback = {
            'USDT': 'binance',  # По умолчанию USDT пары - Binance
            'BUSD': 'binance',
            'USD': 'bybit',      # USD суффикс чаще на Bybit
        }
        
        logger.info("SignalAdapter initialized")
    
    def adapt_signal(self, ws_signal: Dict) -> Dict:
        """
        Преобразует один WebSocket сигнал в формат бота
        
        Args:
            ws_signal: Сигнал от WebSocket сервера
            
        Returns:
            Dict в формате бота
        """
        try:
            # Определяем exchange
            trading_pair_id = ws_signal.get('trading_pair_id')
            exchange = self._determine_exchange(trading_pair_id, ws_signal.get('pair_symbol'))
            
            # Преобразуем timestamp из строки в datetime
            created_at_str = ws_signal.get('created_at')
            if isinstance(created_at_str, str):
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            else:
                created_at = datetime.now(timezone.utc)
            
            # Вычисляем wave_timestamp (округление до 15 минут)
            wave_timestamp = self._calculate_wave_timestamp(created_at)
            
            # Создаем адаптированный сигнал
            adapted = {
                'id': ws_signal.get('id'),
                'symbol': ws_signal.get('pair_symbol'),
                'action': ws_signal.get('recommended_action'),
                'score_week': float(ws_signal.get('score_week', 0)),
                'score_month': float(ws_signal.get('score_month', 0)),
                'created_at': created_at,
                'exchange': exchange,
                'wave_timestamp': wave_timestamp,
                # Дополнительные поля для совместимости
                'timestamp': created_at,
                'is_active': True,
                'signal_type': ws_signal.get('recommended_action')
            }
            
            return adapted
            
        except Exception as e:
            logger.error(f"Error adapting signal {ws_signal.get('id')}: {e}")
            raise
    
    def adapt_signals(self, ws_signals: List[Dict]) -> List[Dict]:
        """
        Преобразует список WebSocket сигналов в формат бота
        
        Args:
            ws_signals: Список сигналов от WebSocket
            
        Returns:
            Список адаптированных сигналов
        """
        adapted_signals = []
        
        for ws_signal in ws_signals:
            try:
                adapted = self.adapt_signal(ws_signal)
                adapted_signals.append(adapted)
            except Exception as e:
                logger.warning(f"Skipping signal {ws_signal.get('id')}: {e}")
                continue
        
        logger.debug(f"Adapted {len(adapted_signals)}/{len(ws_signals)} signals")
        return adapted_signals
    
    def _determine_exchange(self, trading_pair_id: int, symbol: str) -> str:
        """
        Определяет exchange по trading_pair_id или символу
        
        Args:
            trading_pair_id: ID торговой пары
            symbol: Символ (например, BTCUSDT)
            
        Returns:
            Имя биржи ('binance' или 'bybit')
        """
        # Проверяем маппинг
        if trading_pair_id in self.trading_pair_mapping:
            return self.trading_pair_mapping[trading_pair_id]
        
        # Fallback: определяем по суффиксу символа
        if symbol:
            for suffix, exchange in self.exchange_fallback.items():
                if symbol.endswith(suffix):
                    logger.debug(f"Exchange for {symbol} determined by suffix: {exchange}")
                    return exchange
        
        # По умолчанию Binance (самая популярная биржа)
        logger.warning(f"Could not determine exchange for trading_pair_id={trading_pair_id}, using binance")
        return 'binance'
    
    def _calculate_wave_timestamp(self, created_at: datetime) -> datetime:
        """
        Вычисляет wave_timestamp (округление до 15 минут)
        
        Логика из repository.py:
        date_trunc('hour', sc.created_at) + 
            interval '15 min' * floor(date_part('minute', sc.created_at) / 15)
        
        Args:
            created_at: Время создания сигнала
            
        Returns:
            Wave timestamp (округлённый до 15 минут)
        """
        # Округляем до начала часа
        hour_start = created_at.replace(minute=0, second=0, microsecond=0)
        
        # Вычисляем количество 15-минутных интервалов
        minutes_into_hour = created_at.minute
        intervals = minutes_into_hour // 15
        
        # Добавляем интервалы к началу часа
        from datetime import timedelta
        wave_ts = hour_start + timedelta(minutes=intervals * 15)
        
        return wave_ts
    
    def update_trading_pair_mapping(self, mapping: Dict[int, str]):
        """
        Обновляет маппинг trading_pair_id -> exchange
        
        Args:
            mapping: Новый маппинг
        """
        self.trading_pair_mapping.update(mapping)
        logger.info(f"Updated trading pair mapping: {len(self.trading_pair_mapping)} pairs")
    
    async def load_trading_pair_mapping_from_db(self, repository):
        """
        Загружает маппинг trading_pair_id -> exchange из БД
        
        Args:
            repository: Database repository instance
        """
        try:
            query = """
                SELECT 
                    tp.id as trading_pair_id,
                    LOWER(ex.exchange_name) as exchange
                FROM public.trading_pairs tp
                JOIN public.exchanges ex ON ex.id = tp.exchange_id
            """
            
            async with repository.pool.acquire() as conn:
                rows = await conn.fetch(query)
                
                mapping = {row['trading_pair_id']: row['exchange'] for row in rows}
                self.update_trading_pair_mapping(mapping)
                
                logger.info(f"Loaded {len(mapping)} trading pairs from database")
                
        except Exception as e:
            logger.error(f"Failed to load trading pair mapping: {e}")
            logger.warning("Will use fallback exchange determination")
