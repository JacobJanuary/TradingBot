# МОНИТОРИНГ СИСТЕМА - ДЕТАЛЬНЫЙ ПЛАН РЕАЛИЗАЦИИ

## 1. АНАЛИЗ БАЗЫ ДАННЫХ

### 1.1 Структура схемы monitoring

База данных `fox_crypto` на PostgreSQL содержит схему `monitoring` с основными таблицами для мониторинга:

#### Основные таблицы:
- **positions** (700 записей, 31 колонка) - позиции торгового бота
- **trades** (903 записи, 17 колонок) - исполненные сделки
- **events** (526,097 записей, 12 колонок) - поток событий системы
- **trailing_stop_state** (351 запись, 24 колонки) - состояния trailing stop
- **orders** (1400 записей, 17 колонок) - ордера на биржах

### 1.2 Детальная документация таблиц

#### ТАБЛИЦА: monitoring.positions

**Назначение:** Хранение всех позиций торгового бота с их текущим состоянием

**Структура:**
| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval() | Primary key |
| symbol | varchar | NO | | Торговый символ (BTCUSDT) |
| exchange | varchar | NO | | Биржа (Binance/Bybit) |
| side | varchar | NO | | LONG/SHORT |
| quantity | numeric | NO | | Размер позиции |
| entry_price | numeric | NO | | Цена входа |
| current_price | numeric | YES | | Текущая цена (кэш) |
| stop_loss_price | numeric | YES | | Уровень стоп-лосса |
| unrealized_pnl | numeric | YES | | Нереализованный PnL |
| status | varchar | NO | 'active' | Статус позиции |
| opened_at | timestamp | YES | now() | Время открытия |
| closed_at | timestamp | YES | | Время закрытия |
| has_trailing_stop | boolean | YES | false | Наличие TS |
| has_stop_loss | boolean | YES | false | Наличие SL |

**Индексы:**
- PRIMARY KEY (id)
- idx_positions_status (status)
- idx_positions_symbol (symbol)
- idx_positions_opened_at (opened_at)
- idx_unique_active_position (symbol, exchange) WHERE status='active'

**Статусы позиций:**
- `active` - активная позиция (72 записи)
- `closed` - закрытая позиция (515 записей)
- `rolled_back` - откатанная позиция (78 записей)
- `canceled` - отмененная (35 записей)

**Частота обновлений:**
- current_price: каждые 5-10 секунд через position_updated события
- unrealized_pnl: пересчитывается при обновлении цены
- status: при изменении состояния позиции

#### ТАБЛИЦА: monitoring.trailing_stop_state

**Назначение:** Хранение состояния trailing stop для каждой позиции

**Структура:**
| Колонка | Тип | Описание |
|---------|-----|----------|
| id | bigint | Primary key |
| symbol | varchar | Символ |
| exchange | varchar | Биржа |
| position_id | bigint | FK -> positions.id |
| state | varchar | inactive/waiting/active/triggered |
| is_activated | boolean | Флаг активации |
| highest_price | numeric | Максимальная цена (для LONG) |
| lowest_price | numeric | Минимальная цена (для SHORT) |
| current_stop_price | numeric | Текущий уровень SL |
| activation_price | numeric | Цена активации |
| entry_price | numeric | Цена входа |
| side | varchar | LONG/SHORT |
| activated_at | timestamp | Время активации |
| last_update_time | timestamp | Последнее обновление |

**Связи:**
- position_id → monitoring.positions.id

#### ТАБЛИЦА: monitoring.events

**Назначение:** Лог всех событий системы

**Типы событий (за последние 24 часа):**
- `position_updated` - 287,230 событий
- `trailing_stop_updated` - 8,380 событий
- `trailing_stop_activated` - 220 событий
- `stop_loss_placed` - 409 событий
- `position_created` - 300 событий
- `signal_executed` - 300 событий
- `wave_detected` / `wave_completed` - 87 событий каждое
- `health_check_failed` - 266 событий
- `position_error` - 68 событий

### 1.3 ER-диаграмма связей

```
monitoring.positions (1) ←──(1:1) monitoring.trailing_stop_state
         │                         (position_id → id)
         │
         ├──(1:M) monitoring.trades
         │         (signal_id reference)
         │
         └──(1:M) monitoring.events
                   (position_id reference)

monitoring.orders (independent - exchange order tracking)
```

### 1.4 Источники данных для UI

| UI Элемент | Источник данных | SQL запрос | Частота обновления |
|------------|----------------|------------|-------------------|
| Активные позиции | monitoring.positions | WHERE status='active' | 1-2 сек |
| Trailing Stop статус | trailing_stop_state | JOIN с positions | 2 сек |
| Поток событий | monitoring.events | ORDER BY created_at DESC | 1 сек |
| Статистика (1ч) | positions + events | Агрегации | 10 сек |

## 2. UI/UX ДИЗАЙН

### 2.1 Wireframe терминального интерфейса

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     FOX CRYPTO TRADING BOT MONITOR v2.0                              │
│  Status: ● RUNNING  │  Uptime: 14h 32m  │  Active: 72/150  │  Exposure: $14,400    │
├────────────────────────────────────────────┬────────────────────────────────────────┤
│                                            │                                        │
│         ACTIVE POSITIONS (72)              │      STATISTICS (Last 1h)              │
│                                            │                                        │
│ ┌──────────────────────────────────────┐  │  Opened:      18 positions            │
│ │Symbol    Side  Entry    Current  PnL │  │  Closed:       5 positions            │
│ │                         Price    %    │  │  TS Active:    8 positions            │
│ ├──────────────────────────────────────┤  │  Win Rate:    60.0%                   │
│ │BTCUSDT  LONG  67890.0  68420.0 +0.78│  │  Total PnL:   +$127.50                │
│ │Binance  13h            NOW      ✓TS │  │  Avg Hold:     8.2 hours              │
│ │                                      │  │                                        │
│ │ETHUSDT  SHORT 3456.0   3420.0  +1.04│  │ ┌────────────────────────────────┐   │
│ │Bybit    2h             NOW      ⏳TS │  │ │    PERFORMANCE CHART (24h)      │   │
│ │                                      │  │ │                                  │   │
│ │SOLUSDT  LONG  178.50   177.20  -0.73│  │ │  PnL: ▂▄█▄▂▄█████▄▂▄            │   │
│ │Binance  45m            NOW      ○TS │  │ │       └─────────────┘            │   │
│ │                                      │  │ │        00:00   12:00   24:00     │   │
│ └──────────────────────────────────────┘  │ └────────────────────────────────┘   │
│                                            │                                        │
│ [↑↓] Navigate  [S] Sort  [F] Filter       │  Alerts: ⚠ 2 old positions (>12h)     │
├────────────────────────────────────────────┴────────────────────────────────────────┤
│                         EVENT STREAM (Real-time)                                     │
│                                                                                      │
│ 02:15:33 [POSITION_CREATED] BTCUSDT LONG @67890.0 size:0.0029 exchange:Binance     │
│ 02:15:34 [STOP_LOSS_PLACED] BTCUSDT stop order placed at 66532.2 (-2.0%)          │
│ 02:16:45 [TS_ACTIVATED] ETHUSDT trailing stop activated at +1.5% profit           │
│ 02:17:12 [TS_UPDATED] ETHUSDT stop loss moved: 3502.0 → 3485.0                   │
│ 02:17:55 [POSITION_CLOSED] SOLUSDT closed with PnL: -$2.30 (-0.73%)              │
│ 02:18:01 [WAVE_DETECTED] New wave detected: 15 signals received                    │
│ 02:18:03 [HEALTH_CHECK] All systems operational, latency: 45ms                     │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
 [Q] Quit  [R] Refresh  [P] Pause  [C] Clear  [H] Help  [T] Toggle Theme
```

### 2.2 Компоненты UI

#### 2.2.1 Header Panel
- Статус бота (RUNNING/STOPPED/ERROR)
- Uptime с момента запуска
- Количество активных позиций / максимум
- Общая exposure в USD

#### 2.2.2 Positions Table
**Колонки:**
- Symbol + Exchange (2 строки)
- Side с цветовой индикацией (LONG=зеленый, SHORT=красный)
- Entry Price + время открытия
- Current Price + "NOW" метка
- PnL в % с цветом
- TS Status: ✓ (active), ⏳ (waiting), ○ (inactive)

**Особенности:**
- Сортировка по любой колонке
- Подсветка старых позиций (>12ч = желтый, >24ч = красный)
- Мигание при критическом PnL (<-1.5%)

#### 2.2.3 Statistics Panel
- Счетчики за последний час
- Mini-график PnL за 24 часа
- Алерты о проблемных позициях

#### 2.2.4 Event Stream
- Цветовая кодировка по типу события
- Автоскролл к новым событиям
- Фильтрация по типу (опционально)

## 3. АРХИТЕКТУРА РЕШЕНИЯ

### 3.1 Компоненты системы

```
┌──────────────────┐
│   PostgreSQL DB  │
│   (Read-only)    │
└────────┬─────────┘
         │ asyncpg
         ▼
┌──────────────────────┐
│   Data Layer         │
│  - Connection Pool   │
│  - Query Manager     │
│  - Models (Pydantic) │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│   Service Layer      │
│  - DataFetcher       │
│  - Formatter         │
│  - Cache Manager     │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│   Textual UI         │
│  - App Controller    │
│  - Widgets           │
│  - Event Handlers   │
└──────────────────────┘
```

### 3.2 Технологический стек

- **Python 3.10+** - основной язык
- **Textual 0.47.1** - TUI framework
- **asyncpg 0.29.0** - async PostgreSQL driver
- **Pydantic 2.5.2** - модели данных и валидация
- **Rich 13.7.0** - форматирование текста

### 3.3 Структура проекта

```
monitor_ui/
├── main.py                      # Entry point
├── config.py                    # Configuration
├── requirements.txt             # Dependencies
│
├── database/
│   ├── __init__.py
│   ├── connection.py           # DB connection pool
│   ├── queries.py              # All SQL queries
│   └── models.py               # Pydantic models
│
├── ui/
│   ├── __init__.py
│   ├── app.py                  # Main Textual App
│   ├── widgets/
│   │   ├── positions_table.py  # Positions display
│   │   ├── events_stream.py    # Event log widget
│   │   ├── statistics.py       # Stats panel
│   │   └── header.py           # Header widget
│   └── styles.py               # UI styling
│
└── services/
    ├── __init__.py
    ├── data_fetcher.py         # Async data polling
    ├── formatter.py            # Data formatting
    └── cache.py               # Caching layer
```

## 4. ПОШАГОВЫЙ ПЛАН РЕАЛИЗАЦИИ

### Phase 1: Foundation (День 1)

#### 1.1 Настройка проекта
```bash
# Создание структуры
mkdir -p monitor_ui/{database,ui/widgets,services}
cd monitor_ui

# Virtual environment
python3 -m venv venv
source venv/bin/activate

# Dependencies
pip install textual==0.47.1 asyncpg==0.29.0 pydantic==2.5.2 rich==13.7.0
```

#### 1.2 Database Layer
```python
# database/connection.py
import asyncpg
from typing import Optional

class DatabasePool:
    _instance: Optional[asyncpg.Pool] = None

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        if not cls._instance:
            cls._instance = await asyncpg.create_pool(
                "postgresql://evgeniyyanvarskiy@localhost:5432/fox_crypto",
                min_size=2,
                max_size=5,
                command_timeout=5.0
            )
        return cls._instance
```

#### 1.3 Models
```python
# database/models.py
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import Optional

class PositionView(BaseModel):
    id: int
    symbol: str
    exchange: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Optional[Decimal]
    stop_loss_price: Optional[Decimal]
    unrealized_pnl: Optional[Decimal]
    status: str
    opened_at: datetime
    has_trailing_stop: bool
    ts_state: Optional[str]
    age_hours: float
    pnl_percent: float
```

### Phase 2: Data Layer (День 2)

#### 2.1 Queries
```python
# database/queries.py
ACTIVE_POSITIONS_QUERY = """
SELECT
    p.id,
    p.symbol,
    p.exchange,
    p.side,
    p.entry_price,
    p.quantity,
    p.current_price,
    p.unrealized_pnl,
    p.stop_loss_price,
    p.opened_at,
    p.has_trailing_stop,
    ts.state as ts_state,
    ts.is_activated as ts_activated,
    EXTRACT(EPOCH FROM (NOW() - p.opened_at)) / 3600 as age_hours,
    CASE
        WHEN p.side = 'LONG' THEN
            (p.current_price - p.entry_price) / p.entry_price * 100
        ELSE
            (p.entry_price - p.current_price) / p.entry_price * 100
    END as pnl_percent
FROM monitoring.positions p
LEFT JOIN monitoring.trailing_stop_state ts
    ON ts.symbol = p.symbol AND ts.exchange = p.exchange
WHERE p.status = 'active'
ORDER BY p.opened_at DESC
"""

RECENT_EVENTS_QUERY = """
SELECT
    created_at,
    event_type,
    event_data,
    symbol,
    exchange
FROM monitoring.events
WHERE created_at > $1
ORDER BY created_at DESC
LIMIT 100
"""

STATISTICS_QUERY = """
WITH hourly_stats AS (
    SELECT
        COUNT(*) FILTER (WHERE opened_at > NOW() - INTERVAL '1 hour') as opened_count,
        COUNT(*) FILTER (WHERE closed_at > NOW() - INTERVAL '1 hour' AND status = 'closed') as closed_count,
        COUNT(*) FILTER (WHERE closed_at > NOW() - INTERVAL '1 hour' AND realized_pnl > 0) as winners,
        COUNT(*) FILTER (WHERE closed_at > NOW() - INTERVAL '1 hour' AND realized_pnl < 0) as losers,
        SUM(realized_pnl) FILTER (WHERE closed_at > NOW() - INTERVAL '1 hour') as total_pnl
    FROM monitoring.positions
)
SELECT * FROM hourly_stats
"""
```

#### 2.2 Data Fetcher
```python
# services/data_fetcher.py
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta
from database.connection import DatabasePool
from database.models import PositionView, EventView, StatsView
from database.queries import ACTIVE_POSITIONS_QUERY

class DataFetcher:
    def __init__(self):
        self.running = False
        self.last_event_time = datetime.now()
        self.positions_cache: List[PositionView] = []
        self.events_cache: List[EventView] = []
        self.stats_cache: Optional[StatsView] = None

    async def fetch_active_positions(self) -> List[PositionView]:
        pool = await DatabasePool.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(ACTIVE_POSITIONS_QUERY)
            return [PositionView(**dict(row)) for row in rows]

    async def start_polling(self):
        self.running = True
        await asyncio.gather(
            self._poll_positions(),
            self._poll_events(),
            self._poll_statistics()
        )

    async def _poll_positions(self):
        while self.running:
            try:
                self.positions_cache = await self.fetch_active_positions()
            except Exception as e:
                logger.error(f"Position fetch error: {e}")
            await asyncio.sleep(1.0)
```

### Phase 3: UI Implementation (Дни 3-4)

#### 3.1 Main App
```python
# ui/app.py
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer
from ui.widgets.positions_table import PositionsTable
from ui.widgets.events_stream import EventsStream
from ui.widgets.statistics import StatisticsPanel
from services.data_fetcher import DataFetcher

class MonitorApp(App):
    CSS_PATH = "styles.css"
    TITLE = "Fox Crypto Trading Bot Monitor"

    def __init__(self):
        super().__init__()
        self.data_fetcher = DataFetcher()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield PositionsTable(id="positions")
            with Vertical(id="right-panel"):
                yield StatisticsPanel(id="stats")
        yield EventsStream(id="events")
        yield Footer()

    async def on_mount(self) -> None:
        # Start data fetching
        asyncio.create_task(self.data_fetcher.start_polling())

        # Schedule UI updates
        self.set_interval(1.0, self.update_positions)
        self.set_interval(1.0, self.update_events)
        self.set_interval(10.0, self.update_statistics)

    async def update_positions(self) -> None:
        positions_widget = self.query_one("#positions", PositionsTable)
        positions_widget.update_data(self.data_fetcher.positions_cache)
```

#### 3.2 Positions Table Widget
```python
# ui/widgets/positions_table.py
from textual.widgets import DataTable
from rich.text import Text
from typing import List
from database.models import PositionView

class PositionsTable(DataTable):
    def on_mount(self) -> None:
        self.add_columns(
            "Symbol", "Side", "Entry", "Current", "PnL %", "TS", "Age"
        )
        self.zebra_stripes = True
        self.cursor_type = "row"

    def update_data(self, positions: List[PositionView]) -> None:
        self.clear()
        for pos in positions:
            # Format data
            symbol_text = f"{pos.symbol}\\n{pos.exchange}"

            # Color code side
            side_text = Text(pos.side)
            side_text.stylize("green" if pos.side == "LONG" else "red")

            # Format PnL with color
            pnl_text = Text(f"{pos.pnl_percent:+.2f}%")
            pnl_text.stylize("green" if pos.pnl_percent > 0 else "red")

            # TS status icon
            ts_icon = "✓" if pos.ts_state == "active" else "⏳" if pos.ts_state == "waiting" else "○"

            # Age formatting with warning color
            age_text = self._format_age(pos.age_hours)
            if pos.age_hours > 12:
                age_text.stylize("yellow")
            if pos.age_hours > 24:
                age_text.stylize("red")

            self.add_row(
                symbol_text, side_text,
                f"{pos.entry_price:.2f}",
                f"{pos.current_price:.2f}",
                pnl_text, ts_icon, age_text
            )

    def _format_age(self, hours: float) -> Text:
        if hours < 1:
            return Text(f"{int(hours * 60)}m")
        elif hours < 24:
            return Text(f"{int(hours)}h {int((hours % 1) * 60)}m")
        else:
            days = int(hours / 24)
            return Text(f"{days}d {int(hours % 24)}h")
```

#### 3.3 Event Stream Widget
```python
# ui/widgets/events_stream.py
from textual.widgets import RichLog
from rich.text import Text
from typing import List
from database.models import EventView

class EventsStream(RichLog):
    EVENT_COLORS = {
        "position_created": "green",
        "position_closed": "blue",
        "stop_loss_placed": "yellow",
        "trailing_stop_activated": "bright_green",
        "trailing_stop_updated": "yellow",
        "position_error": "red",
        "wave_detected": "cyan",
        "health_check_failed": "red"
    }

    def on_mount(self) -> None:
        self.max_lines = 50
        self.auto_scroll = True

    def add_events(self, events: List[EventView]) -> None:
        for event in events:
            # Format timestamp
            time_str = event.created_at.strftime("%H:%M:%S")

            # Get color for event type
            color = self.EVENT_COLORS.get(event.event_type, "white")

            # Format message
            event_text = Text()
            event_text.append(f"{time_str} ", style="dim")
            event_text.append(f"[{event.event_type.upper()}] ", style=f"bold {color}")

            # Add event details
            if event.symbol:
                event_text.append(f"{event.symbol} ")
            if event.event_data:
                event_text.append(str(event.event_data))

            self.write(event_text)
```

#### 3.4 Statistics Panel
```python
# ui/widgets/statistics.py
from textual.widgets import Static
from textual.containers import Grid
from rich.panel import Panel
from rich.table import Table

class StatisticsPanel(Static):
    def compose(self) -> ComposeResult:
        yield Static(id="stats-content")

    def update_stats(self, stats: StatsView) -> None:
        # Create rich table for statistics
        table = Table(show_header=False, box=None, padding=0)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        # Add rows
        table.add_row("Opened (1h):", str(stats.opened_count))
        table.add_row("Closed (1h):", str(stats.closed_count))
        table.add_row("TS Active:", str(stats.ts_active_count))

        # Win rate with color
        win_rate = (stats.winners / max(stats.closed_count, 1)) * 100
        win_rate_style = "green" if win_rate >= 50 else "red"
        table.add_row("Win Rate:", f"[{win_rate_style}]{win_rate:.1f}%[/]")

        # Total PnL with color
        pnl_style = "green" if stats.total_pnl > 0 else "red"
        table.add_row("Total PnL:", f"[{pnl_style}]${stats.total_pnl:+.2f}[/]")

        # Update widget
        content_widget = self.query_one("#stats-content", Static)
        content_widget.update(Panel(table, title="Statistics (1h)", border_style="blue"))
```

### Phase 4: Styling & Polish (День 5)

#### 4.1 CSS Styling
```css
/* ui/styles.css */
MonitorApp {
    background: $surface;
}

#main-container {
    height: 60%;
}

#left-panel {
    width: 65%;
    padding: 1;
}

#right-panel {
    width: 35%;
    padding: 1;
}

#events {
    height: 35%;
    border: solid $primary;
    padding: 1;
}

PositionsTable {
    height: 100%;
    border: solid $primary;
}

StatisticsPanel {
    height: 50%;
    margin-bottom: 1;
}

.warning {
    background: $warning;
}

.error {
    background: $error;
}

.success {
    color: $success;
}
```

#### 4.2 Main Entry Point
```python
# main.py
#!/usr/bin/env python3
import asyncio
import argparse
from ui.app import MonitorApp
from database.connection import DatabasePool

async def main():
    parser = argparse.ArgumentParser(description="Trading Bot Monitor UI")
    parser.add_argument("--db-host", default="localhost", help="Database host")
    parser.add_argument("--db-port", default=5432, type=int, help="Database port")
    parser.add_argument("--db-name", default="fox_crypto", help="Database name")
    parser.add_argument("--db-user", default="evgeniyyanvarskiy", help="Database user")
    args = parser.parse_args()

    # Initialize database
    await DatabasePool.initialize(
        host=args.db_host,
        port=args.db_port,
        database=args.db_name,
        user=args.db_user
    )

    # Run app
    app = MonitorApp()
    await app.run_async()

if __name__ == "__main__":
    asyncio.run(main())
```

## 5. ТЕХНИЧЕСКИЕ ДЕТАЛИ

### 5.1 SQL Оптимизация

```sql
-- Создать материализованное представление для статистики
CREATE MATERIALIZED VIEW monitoring.position_stats_hourly AS
SELECT
    date_trunc('hour', opened_at) as hour,
    COUNT(*) as opened_count,
    COUNT(*) FILTER (WHERE status = 'closed') as closed_count,
    AVG(EXTRACT(EPOCH FROM (closed_at - opened_at))) as avg_duration_seconds
FROM monitoring.positions
WHERE opened_at > NOW() - INTERVAL '24 hours'
GROUP BY date_trunc('hour', opened_at);

-- Обновлять каждые 5 минут
CREATE INDEX idx_position_stats_hour ON monitoring.position_stats_hourly(hour);
```

### 5.2 Connection Pooling

```python
# Оптимальные настройки для read-only мониторинга
POOL_CONFIG = {
    "min_size": 2,        # Минимум соединений
    "max_size": 5,        # Максимум соединений
    "max_queries": 50000, # Queries per connection
    "max_inactive_connection_lifetime": 300.0,
    "command_timeout": 5.0,
    "query_timeout": 3.0
}
```

### 5.3 Error Handling Strategy

```python
class ResilientDataFetcher:
    def __init__(self):
        self.error_count = 0
        self.max_errors = 3
        self.last_good_data = None

    async def fetch_with_fallback(self):
        try:
            data = await self.fetch_from_db()
            self.error_count = 0
            self.last_good_data = data
            return data
        except Exception as e:
            self.error_count += 1
            if self.error_count >= self.max_errors:
                # Show warning in UI
                self.show_db_error_warning()
            # Return cached data
            return self.last_good_data or []
```

## 6. ТЕСТИРОВАНИЕ

### 6.1 Unit Tests

```python
# tests/test_data_fetcher.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.data_fetcher import DataFetcher

@pytest.mark.asyncio
async def test_fetch_positions():
    fetcher = DataFetcher()
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetch.return_value = [
        {"id": 1, "symbol": "BTCUSDT", "side": "LONG", ...}
    ]

    positions = await fetcher.fetch_active_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "BTCUSDT"
```

### 6.2 Integration Tests

```python
# tests/test_integration.py
@pytest.mark.asyncio
async def test_full_data_flow():
    # Create test database
    # Insert test data
    # Start app
    # Verify UI updates
    pass
```

### 6.3 Performance Benchmarks

Целевые метрики:
- Запуск приложения: < 2 секунды
- Обновление позиций: < 100ms
- Обновление событий: < 50ms
- Потребление памяти: < 100MB
- CPU использование: < 5%

## 7. DEPLOYMENT

### 7.1 Установка

```bash
# Clone repository
git clone https://github.com/yourname/trading-bot-monitor.git
cd trading-bot-monitor

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure database
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=fox_crypto
export DB_USER=evgeniyyanvarskiy
```

### 7.2 Запуск

```bash
# Production mode
python main.py

# With custom database
python main.py --db-host remote.host --db-port 5432

# Debug mode
python main.py --debug

# Mock mode (without database)
python main.py --mock
```

### 7.3 Systemd Service

```ini
[Unit]
Description=Trading Bot Monitor UI
After=network.target postgresql.service

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/trading-bot-monitor
Environment="PATH=/opt/trading-bot-monitor/venv/bin"
ExecStart=/opt/trading-bot-monitor/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 8. ROADMAP

### Completed ✅
- [x] Database structure analysis
- [x] UI/UX design
- [x] Architecture planning
- [x] Implementation plan

### Phase 1 (Current)
- [ ] Basic database connection
- [ ] Core data models
- [ ] Simple position display

### Phase 2
- [ ] Event stream widget
- [ ] Statistics panel
- [ ] Real-time updates

### Phase 3
- [ ] Advanced filtering
- [ ] Position details modal
- [ ] Keyboard shortcuts

### Future Enhancements
- [ ] Historical view
- [ ] PnL charts
- [ ] Export to CSV
- [ ] Alert system
- [ ] Multi-page navigation

## APPENDIX

### A. Альтернативные подходы

**Рассмотренные но отклоненные:**
- Web UI (Flask/FastAPI) - требует браузер, сложнее deployment
- Desktop GUI (Tkinter/PyQt) - тяжелые зависимости
- Curses - слишком низкоуровневый, мало возможностей

**Почему Textual:**
- Современный TUI framework
- Reactive updates
- Rich formatting support
- CSS-like styling
- Async native

### B. Troubleshooting

**Проблема:** Database connection timeout
**Решение:** Проверить PostgreSQL запущен, порт открыт, credentials верные

**Проблема:** High CPU usage
**Решение:** Увеличить polling intervals, оптимизировать queries

**Проблема:** UI не обновляется
**Решение:** Проверить async tasks запущены, нет блокирующих операций

### C. Полезные команды

```bash
# Monitor database connections
psql -c "SELECT * FROM pg_stat_activity WHERE datname='fox_crypto'"

# Check table sizes
psql -c "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname='monitoring'"

# Test connection
python -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('postgresql://user@localhost/db'))"
```

## ЗАКЛЮЧЕНИЕ

Данный план предоставляет полную roadmap для реализации системы мониторинга торгового бота с использованием Textual и PostgreSQL. Основные преимущества решения:

1. **Read-only безопасность** - только чтение из БД
2. **Real-time обновления** - задержка 1-2 секунды
3. **Легковесность** - работает в терминале
4. **Масштабируемость** - async архитектура
5. **Расширяемость** - модульная структура

Следуя этому плану, можно реализовать полнофункциональную систему мониторинга за 5-7 дней.