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
        "trading_pair_id": 1234,
        "exchange_id": 1  # 1=Binance, 2=Bybit
    }
    
    Формат бота:
    {
        "id": int,
        "symbol": str,
        "action": str,
        "score_week": float,
        "score_month": float,
        "created_at": datetime,
        "exchange": str,  # 'binance' или 'bybit'
        "wave_timestamp": datetime
    }
    """
    
    def __init__(self):
        """
        Signal Adapter для преобразования WebSocket сигналов.
        Биржа определяется напрямую из поля exchange_id в сигнале.
        """
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
            # Определяем exchange напрямую из exchange_id
            exchange_id = ws_signal.get('exchange_id')
            exchange = self._determine_exchange(exchange_id)
            
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
        
        
        # ✅ PROTECTIVE SORT: Ensure signals are sorted DESC by score_week, score_month
        # This is a safety measure even if server sends pre-sorted data
        sorted_signals = sorted(
            adapted_signals,
            key=lambda s: (s.get('score_week', 0), s.get('score_month', 0)),
            reverse=True
        )
        
        logger.debug(f"Adapted and sorted {len(sorted_signals)}/{len(ws_signals)} signals by score_week DESC")
        return sorted_signals
    
    def _determine_exchange(self, exchange_id: int) -> str:
        """
        Определяет exchange по exchange_id из WebSocket сигнала
        
        Args:
            exchange_id: ID биржи (1=Binance, 2=Bybit)
            
        Returns:
            Имя биржи ('binance' или 'bybit')
        """
        if exchange_id == 1:
            return 'binance'
        elif exchange_id == 2:
            return 'bybit'
        else:
            logger.warning(f"Unknown exchange_id={exchange_id}, defaulting to binance")
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
    
