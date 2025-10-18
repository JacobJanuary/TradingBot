# POSITION SYNCHRONIZATION - EXACT CODE PATHS

## PATH 1: PHANTOM DETECTION AND CLOSURE

### Entry Point
File: `core/position_synchronizer.py`
Method: `synchronize_exchange()` (lines 126-266)

### Step-by-Step Execution

#### Step 1: Fetch Exchange Positions
```python
# Lines 154-157
exchange_positions = await self._fetch_exchange_positions(exchange, exchange_name)
self.stats['exchange_positions'] += len(exchange_positions)
logger.info(f"  Found {len(exchange_positions)} positions on exchange")
```

Location: `_fetch_exchange_positions()` (lines 268-337)

**What happens:**
1. Calls `exchange.fetch_positions()`
2. Filters by PHASE 1: `contracts > 0`
3. For Binance (PHASE 2): Validates `info.get('positionAmt') > 0`
4. For Bybit (PHASE 3): Validates `info.get('size') > 0`
5. Returns only REAL active positions

Result: `exchange_positions = [REAL_POS_1, REAL_POS_2, ...]`

#### Step 2: Fetch Database Positions
```python
# Lines 147-149
all_db_positions = await self.repository.get_open_positions()
db_positions = [pos for pos in all_db_positions if pos.get('exchange') == exchange_name]
self.stats['db_positions'] += len(db_positions)
```

Location: `database/repository.py` - `get_open_positions()` (lines 448-462)

**What happens:**
```sql
SELECT id, symbol, exchange, side, entry_price, current_price,
       quantity, leverage, stop_loss, take_profit,
       status, pnl, pnl_percentage, trailing_activated,
       has_trailing_stop, created_at, updated_at
FROM monitoring.positions
WHERE status = 'active'
ORDER BY created_at DESC
```

Result: `db_positions = [DB_POS_1, DB_POS_2, ...]` (only ACTIVE positions)

#### Step 3: Create Normalized Symbol Maps
```python
# Lines 161-162
db_map = {normalize_symbol(pos['symbol']): pos for pos in db_positions}
exchange_map = {normalize_symbol(pos['symbol']): pos for pos in exchange_positions}
```

**normalization:**
- `HIGHUSDT` (DB) → `HIGHUSDT` (normalized)
- `HIGH/USDT:USDT` (exchange) → `HIGHUSDT` (normalized)

Result: 
```python
db_map = {'BTCUSDT': db_pos_1, 'ETHUSDT': db_pos_2, ...}
exchange_map = {'BTCUSDT': ex_pos_1, ...}
```

#### Step 4: Detect Phantom Positions
```python
# Lines 165-248
for symbol, db_pos in db_map.items():
    if symbol in exchange_map:
        # Position exists - verify quantity
        ...
    else:
        # PHANTOM DETECTED!
        logger.warning(f"  🗑️ {symbol}: PHANTOM position (not on exchange)")
        
        # CALL CLOSURE
        await self._close_phantom_position(db_pos)
        result['closed_phantom'].append(symbol)
        self.stats['closed_phantom'] += 1
```

#### Step 5: Close Phantom Position
Location: `_close_phantom_position()` (lines 339-380)

```python
async def _close_phantom_position(self, db_position: Dict):
    position_id = db_position['id']
    symbol = db_position['symbol']
    exchange = db_position.get('exchange', 'unknown')
    
    # CLOSE IN DATABASE
    await self.repository.close_position(
        position_id=position_id,
        close_price=db_position.get('current_price', 0),
        pnl=0,
        pnl_percentage=0,
        reason='PHANTOM_ON_SYNC'  # ← Explicit reason
    )
    
    logger.info(f"    Closed phantom position: {symbol} (ID: {position_id})")
    
    # LOG EVENT
    event_logger = get_event_logger()
    if event_logger:
        await event_logger.log_event(
            EventType.PHANTOM_POSITION_CLOSED,
            {
                'symbol': symbol,
                'exchange': exchange,
                'position_id': position_id,
                'reason': 'not_on_exchange'
            },
            symbol=symbol,
            exchange=exchange,
            severity='WARNING'
        )
```

#### Step 6: Database Update
Location: `database/repository.py` - `close_position()` (lines 348-399)

```python
async def close_position(self, position_id: int,
                        close_price: float = None,
                        pnl: float = None,
                        pnl_percentage: float = None,
                        reason: str = None,
                        exit_data: Dict = None):
    
    # Parse parameters
    realized_pnl = pnl or 0
    exit_reason = reason or 'manual'
    current_price = close_price
    pnl_percent = pnl_percentage
    
    # Execute update
    query = """
        UPDATE monitoring.positions
        SET status = 'closed',
            pnl = $1,
            exit_reason = $2,
            current_price = COALESCE($3, current_price),
            pnl_percentage = COALESCE($4, pnl_percentage),
            closed_at = NOW(),
            updated_at = NOW()
        WHERE id = $5
    """
    
    async with self.pool.acquire() as conn:
        await conn.execute(
            query,
            realized_pnl,  # pnl = 0
            exit_reason,   # exit_reason = 'PHANTOM_ON_SYNC'
            current_price,
            pnl_percent,
            position_id
        )
```

**Result:** Position marked as `closed` in database.

---

## PATH 2: SYNC CLEANUP (Alternative Flow)

File: `core/position_manager.py`
Method: `sync_exchange_positions()` (lines 573-768)

### Detection Phase
```python
# Lines 604-612
db_positions_list = await self.repository.get_open_positions()
db_symbols = {
    p['symbol'] for p in db_positions_list
    if p.get('exchange') == exchange_name
}

# Compare with active exchange symbols
active_symbols = {normalize_symbol(p['symbol']) for p in active_positions}

# Find positions to close
db_positions_to_close = []
for symbol, pos_state in list(self.positions.items()):
    if pos_state.exchange == exchange_name and symbol not in active_symbols:
        db_positions_to_close.append(pos_state)
```

### Closure Phase
```python
# Lines 621-673
if db_positions_to_close:
    logger.warning(f"Found {len(db_positions_to_close)} positions in DB but not on {exchange_name}")
    for pos_state in db_positions_to_close:
        logger.info(f"Closing orphaned position: {pos_state.symbol}")
        
        if pos_state.id:
            # Log estimated exit
            try:
                exit_side = 'sell' if pos_state.side == 'long' else 'buy'
                await self.repository.create_order({
                    'position_id': str(pos_state.id),
                    'exchange': pos_state.exchange,
                    'symbol': pos_state.symbol,
                    'order_id': None,
                    'type': 'MARKET',
                    'side': exit_side,
                    'size': pos_state.quantity,
                    'price': pos_state.current_price,
                    'status': 'FILLED',
                    'filled': pos_state.quantity,
                    'remaining': 0,
                    'fee': 0,
                    'fee_currency': 'USDT'
                })
                await self.repository.create_trade({...})  # Similar structure
            except Exception as e:
                logger.warning(f"Failed to log sync_cleanup exit: {e}")
            
            # CLOSE IN DATABASE
            await self.repository.close_position(
                pos_state.id,
                pos_state.current_price or 0.0,
                pos_state.unrealized_pnl or 0.0,
                pos_state.unrealized_pnl_percent or 0.0,
                'sync_cleanup'  # ← Different reason
            )
        
        # REMOVE FROM CACHE
        self.positions.pop(pos_state.symbol, None)
        logger.info(f"✅ Closed orphaned position: {pos_state.symbol}")
```

---

## PATH 3: MANUAL CLOSURE WITH FULL CLEANUP

File: `core/position_manager.py`
Method: `close_position()` (lines 1876-2076)

### Exchange Closure
```python
# Lines 1892-1893
success = await exchange.close_position(symbol)
```

### Exit Logging
```python
# Lines 1906-1945
try:
    exit_side = 'sell' if position.side == 'long' else 'buy'
    await self.repository.create_order({...})
    await self.repository.create_trade({...})
    logger.debug(f"📝 Exit order logged to database")
except Exception as e:
    logger.warning(f"Failed to log exit order: {e}")
```

### Database Closure
```python
# Lines 1947-1954
await self.repository.close_position(
    position.id,
    exit_price,
    realized_pnl,
    realized_pnl_percent,
    reason
)
```

### Statistics Update
```python
# Lines 1956-1963
self.stats['positions_closed'] += 1
self.stats['total_pnl'] += Decimal(str(realized_pnl))

if realized_pnl > 0:
    self.stats['win_count'] += 1
else:
    self.stats['loss_count'] += 1
```

### Cache Cleanup
```python
# Lines 1965-1968
del self.positions[symbol]
self.position_count -= 1
self.total_exposure -= Decimal(str(position.quantity * position.entry_price))
```

### Trailing Stop Removal
```python
# Lines 1970-1991
trailing_manager = self.trailing_managers.get(position.exchange)
if trailing_manager:
    await trailing_manager.on_position_closed(symbol, realized_pnl)
    
    if position.has_trailing_stop:
        event_logger.log_event(
            EventType.TRAILING_STOP_REMOVED,
            {
                'symbol': symbol,
                'position_id': position.id,
                'reason': 'position_closed',
                'realized_pnl': float(realized_pnl)
            },
            severity='INFO'
        )
```

### Stop Loss Cleanup
```python
# Lines 2020-2055
try:
    open_orders = await exchange.exchange.fetch_open_orders(symbol)
    
    for order in open_orders:
        order_type = order.get('type', '').lower()
        is_stop = 'stop' in order_type or order_type in ['stop_market', 'stop_loss', 'stop_loss_limit']
        
        if is_stop:
            logger.info(f"🧹 Cleaning up SL order {order['id']} for closed position {symbol}")
            await exchange.exchange.cancel_order(order['id'], symbol)
            
            event_logger.log_event(
                EventType.ORPHANED_SL_CLEANED,
                {
                    'symbol': symbol,
                    'order_id': order['id'],
                    'order_type': order.get('type'),
                    'reason': 'position_closed'
                },
                severity='INFO'
            )
except Exception as cleanup_error:
    logger.warning(f"Failed to cleanup SL orders for {symbol}: {cleanup_error}")
```

---

## PATH 4: STARTUP SYNCHRONIZATION WITH CACHE RELOAD

File: `core/position_synchronizer.py`
Function: `synchronize_positions_on_startup()` (lines 589-615)

```python
async def synchronize_positions_on_startup(position_manager) -> Dict:
    """Helper function to synchronize positions during startup"""
    
    logger.info("🔄 Synchronizing positions with exchanges...")
    
    # Create synchronizer
    synchronizer = PositionSynchronizer(
        repository=position_manager.repository,
        exchanges=position_manager.exchanges
    )
    
    # Run synchronization (calls PATH 1: PHANTOM DETECTION)
    results = await synchronizer.synchronize_all_exchanges()
    
    # CRITICAL: Update position manager's internal state
    # Clear cache
    position_manager.positions.clear()
    position_manager.total_exposure = Decimal('0')
    
    # Reload ONLY active positions
    await position_manager.load_positions_from_db()
    
    logger.info("✅ Position synchronization complete")
    
    return results
```

### What `load_positions_from_db()` Does
Location: `core/position_manager.py` (lines 319-570)

```python
async def load_positions_from_db(self):
    """Load open positions from database on startup"""
    
    # Step 1: Re-synchronize (nested call)
    await self.synchronize_with_exchanges()  # Call synchronizer again
    
    # Step 2: Load verified positions
    positions = await self.repository.get_open_positions()
    # Query: WHERE status = 'active'
    # Result: CLOSED positions excluded naturally
    
    verified_positions = []
    
    for pos in positions:
        exchange_name = pos['exchange']
        symbol = pos['symbol']
        
        if exchange_name in self.exchanges:
            try:
                # Double-check position exists on exchange
                position_exists = await self.verify_position_exists(symbol, exchange_name)
                
                if position_exists:
                    verified_positions.append(pos)
                    logger.debug(f"✅ Verified position exists on exchange: {symbol}")
                else:
                    logger.warning(f"🗑️ PHANTOM detected during load: {symbol}")
                    
                    # Close phantom immediately
                    await self.repository.close_position(
                        pos['id'],
                        0.0,
                        0.0,
                        0.0,
                        'PHANTOM_ON_LOAD'
                    )
            except Exception as e:
                logger.error(f"Error verifying position {symbol}: {e}")
                continue
    
    # Step 3: Use only verified positions
    positions = verified_positions
    
    # Step 4: Load into cache (only ACTIVE/VERIFIED positions)
    for pos in positions:
        position_state = PositionState(...)
        self.positions[pos['symbol']] = position_state
        self.total_exposure += Decimal(str(position_value))
    
    logger.info(f"📊 Loaded {len(self.positions)} positions from database")
    
    # ... Continue with SL setup, trailing stop init, etc.
```

---

## KEY ENTRY POINTS

### 1. Automatic Sync (Periodic)
Location: `core/position_manager.py` - `start_periodic_sync()` (lines 769-800)

```python
while True:
    await asyncio.sleep(self.sync_interval)  # 120 seconds
    
    for exchange_name in self.exchanges.keys():
        await self.sync_exchange_positions(exchange_name)  # PATH 2
    
    await self.check_positions_protection()
    await self.handle_real_zombies()
    await self.cleanup_zombie_orders()
    await self.check_positions_protection()
```

### 2. Startup Sync
Location: `main.py` or startup sequence

```python
await synchronize_positions_on_startup(position_manager)  # PATH 4
```

### 3. Manual Close
Location: Called externally or by protection system

```python
await position_manager.close_position(symbol, reason='manual')  # PATH 3
```

---

## VERIFICATION: Database State Changes

### Before: Position is Active
```sql
SELECT * FROM monitoring.positions WHERE symbol='HIGHUSDT' AND status='active';

id | symbol   | status | closed_at | exit_reason | pnl | pnl_percentage
1  | HIGHUSDT | active | NULL      | NULL        | 0   | NULL
```

### After: Phantom Detection → Closure
```sql
UPDATE monitoring.positions
SET status = 'closed',
    closed_at = NOW(),
    exit_reason = 'PHANTOM_ON_SYNC',
    pnl = 0,
    pnl_percentage = 0
WHERE id = 1;

Result:
id | symbol   | status | closed_at           | exit_reason       | pnl | pnl_percentage
1  | HIGHUSDT | closed | 2025-10-18 14:30:45 | PHANTOM_ON_SYNC   | 0   | 0
```

### Database Query Returns Closed Position Filtered Out
```sql
SELECT * FROM monitoring.positions 
WHERE status = 'active' AND symbol='HIGHUSDT';

-- Result: NO ROWS (position is closed, not returned)
```

### Cache State Changes

Before:
```python
self.positions = {
    'HIGHUSDT': PositionState(id=1, symbol='HIGHUSDT', ...),
    'BTCUSDT': PositionState(id=2, symbol='BTCUSDT', ...)
}
```

After:
```python
self.positions = {
    'BTCUSDT': PositionState(id=2, symbol='BTCUSDT', ...)
}
# HIGHUSDT removed via:
# - self.positions.pop('HIGHUSDT', None)  OR
# - del self.positions['HIGHUSDT']
```

---

## CONCLUSION

The position synchronization system has clear, well-implemented code paths:

1. **Phantom Detection** - Compares normalized symbols between exchange and DB
2. **Immediate Closure** - Updates DB with status='closed' and explicit reason
3. **Cache Removal** - Removes from self.positions dict
4. **Monitoring Stop** - Natural exclusion via DB filtering + explicit cleanup

All transitions are logged and tracked for audit trail.

