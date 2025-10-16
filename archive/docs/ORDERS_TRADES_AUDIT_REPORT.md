# 🔍 AUDIT REPORT: orders & trades Tables - Deep Investigation

**Date**: 2025-10-16
**Status**: INVESTIGATION COMPLETE - PLANNING PHASE
**Severity**: MEDIUM (functionality works, but audit trail missing)

---

## 📊 EXECUTIVE SUMMARY

**Problem**: Tables `monitoring.orders` and `monitoring.trades` are EMPTY despite bot actively trading.

**Root Cause**: `AtomicPositionManager` (used in 100% of trades) does NOT log orders/trades to database.

**Impact**:
- ❌ No audit trail of executed orders
- ❌ No trade history for analysis
- ❌ Cannot reconstruct position entry/exit details
- ❌ Missing data for performance metrics calculation

---

## 🏗️ DATABASE SCHEMA ANALYSIS

### Table: `monitoring.orders`

**Purpose**: Track ALL orders placed on exchanges (entry, SL, TP, etc.)

**Schema**:
```sql
- id (SERIAL PK)
- position_id (VARCHAR 100) -- Links to positions table
- exchange (VARCHAR 50)
- symbol (VARCHAR 20)
- order_id (VARCHAR 100) -- Exchange order ID
- client_order_id (VARCHAR 100)
- type (VARCHAR 20) -- MARKET, LIMIT, STOP_LOSS, etc.
- side (VARCHAR 10) -- buy, sell
- size (DECIMAL 20,8)
- price (DECIMAL 20,8)
- status (VARCHAR 20) -- NEW, FILLED, CANCELED, etc.
- filled (DECIMAL 20,8)
- remaining (DECIMAL 20,8)
- fee (DECIMAL 20,8)
- fee_currency (VARCHAR 10)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

**Current State**: 0 rows
**Expected**: Should have entries for EVERY order placed (entry + SL minimum)

---

### Table: `monitoring.trades`

**Purpose**: Track EXECUTED trades (filled orders)

**Schema**:
```sql
- id (SERIAL PK)
- signal_id (INTEGER) -- Optional link to signal
- symbol (VARCHAR 20)
- exchange (VARCHAR 50)
- side (VARCHAR 10) -- buy, sell
- order_type (VARCHAR 20)
- quantity (DECIMAL 20,8)
- price (DECIMAL 20,8)
- executed_qty (DECIMAL 20,8)
- average_price (DECIMAL 20,8)
- order_id (VARCHAR 100) -- Links to exchange order
- client_order_id (VARCHAR 100)
- status (VARCHAR 20)
- fee (DECIMAL 20,8)
- fee_currency (VARCHAR 10)
- executed_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

**Current State**: 0 rows
**Expected**: Should have entry for EVERY filled trade

---

### Table: `monitoring.positions`

**Schema includes**:
```sql
- exchange_order_id (VARCHAR 100) -- Entry order ID
```

**Current State**: Has `exchange_order_id` populated (e.g., "ee505a33-39aa-4a75-9686-450c8102ae62")
**Note**: This field is populated, but no corresponding record in `orders` table!

---

## 🔄 POSITION LIFECYCLE ANALYSIS

### Current Flow (ATOMIC PATH)

```
1. Signal Received
   ↓
2. PositionManager.open_position() called
   ↓
3. AtomicPositionManager.open_position_atomic() called
   ↓
4. CREATE position record in DB (status=PENDING_ENTRY)
   |
   ├─ position_id: 55
   ├─ symbol: MNTUSDT
   ├─ status: pending_entry
   |
   ↓
5. PLACE entry order on exchange
   |
   ├─ ExchangeManager.create_market_order()
   ├─ Returns: OrderResult object
   ├─ order_id: "ee505a33-39aa-4a75-9686-450c8102ae62"
   |
   ↓
6. UPDATE position (status=ENTRY_PLACED)
   |
   ├─ exchange_order_id: "ee505a33-..."
   ├─ current_price: execution_price
   ├─ status: entry_placed
   |
   ⚠️ NO RECORD IN orders TABLE!
   ⚠️ NO RECORD IN trades TABLE!
   |
   ↓
7. PLACE stop-loss order
   |
   ├─ StopLossManager.set_stop_loss()
   ├─ Returns: sl_result dict
   |
   ⚠️ NO RECORD IN orders TABLE!
   |
   ↓
8. UPDATE position (status=ACTIVE)
   |
   ├─ stop_loss_price: 2.154036
   ├─ status: active
   |
   ↓
9. RETURN success to PositionManager
   |
   ↓
10. Position added to in-memory tracking
```

### Legacy Flow (NON-ATOMIC PATH)

```
[DEPRECATED - Not used anymore]

1-6. [Same as above]
   ↓
7. repository.create_trade() ✅
   |
   ├─ Creates record in trades table
   |
   ↓
8. repository.create_position()
   ↓
9. [Rest of flow]
```

**Key Finding**: Legacy path DOES create trades, but is not used!

---

## 💡 WHEN TO CREATE RECORDS

### `orders` Table - WHEN:

1. **Entry Order Placed** (Step 5 in lifecycle)
   - type: "MARKET"
   - status: "NEW" → "FILLED"
   - Links to position via position_id

2. **Stop-Loss Order Placed** (Step 7)
   - type: "STOP_LOSS" or "STOP_MARKET"
   - status: "NEW" (pending)
   - Links to position via position_id

3. **Stop-Loss Order Updated** (Trailing Stop)
   - type: "STOP_LOSS"
   - status: "MODIFIED" or create new record
   - Links to position

4. **Take-Profit Order Placed** (if used)
   - type: "TAKE_PROFIT"
   - status: "NEW"

5. **Position Closed** (manual or SL/TP triggered)
   - type: "MARKET" (for manual close)
   - status: "FILLED"

### `trades` Table - WHEN:

1. **Entry Order FILLED** (Step 5)
   - Side matches position.side (buy for long, sell for short)
   - quantity = position.quantity
   - price = execution price
   - status: "FILLED"

2. **Position Closed** (exit trade)
   - Side opposite to position.side
   - quantity = position.quantity
   - price = exit price
   - status: "FILLED"

**Note**: SL/TP orders should be in `orders`, but only create `trades` record when they EXECUTE (position closes).

---

## 📝 WHAT TO RECORD

### For Entry Order:

**orders table**:
```python
{
    'position_id': str(position_id),  # Link to positions.id
    'exchange': exchange,
    'symbol': symbol,
    'order_id': entry_order.id,  # Exchange order ID
    'client_order_id': entry_order.clientOrderId,
    'type': 'MARKET',
    'side': side,  # 'buy' or 'sell'
    'size': quantity,
    'price': entry_order.price or exec_price,
    'status': 'FILLED',
    'filled': quantity,
    'remaining': 0,
    'fee': entry_order.fee or 0,
    'fee_currency': 'USDT'
}
```

**trades table**:
```python
{
    'signal_id': signal_id,  # Optional
    'symbol': symbol,
    'exchange': exchange,
    'side': side,
    'order_type': 'MARKET',
    'quantity': quantity,
    'price': exec_price,
    'executed_qty': quantity,
    'average_price': exec_price,
    'order_id': entry_order.id,
    'client_order_id': entry_order.clientOrderId,
    'status': 'FILLED',
    'fee': entry_order.fee or 0,
    'fee_currency': 'USDT'
}
```

### For Stop-Loss Order:

**orders table ONLY** (not in trades until executed):
```python
{
    'position_id': str(position_id),
    'exchange': exchange,
    'symbol': symbol,
    'order_id': sl_result.get('orderId'),
    'client_order_id': sl_result.get('clientOrderId'),
    'type': 'STOP_MARKET' or 'STOP_LOSS',
    'side': 'sell' if position_side == 'long' else 'buy',
    'size': quantity,
    'price': stop_loss_price,
    'status': 'NEW',  # Pending, not filled yet
    'filled': 0,
    'remaining': quantity,
    'fee': 0,
    'fee_currency': 'USDT'
}
```

---

## 🔍 CODE LOCATIONS

### Where Orders Are Created (Exchange Level):

1. **ExchangeManager.create_market_order()** (`core/exchange_manager.py:334`)
   - Returns: `OrderResult` object
   - Contains: id, symbol, side, amount, price, filled, status

2. **StopLossManager.set_stop_loss()** (`core/stop_loss_manager.py`)
   - Returns: Dict with order details
   - Contains: orderId, stopPrice, status

### Where Orders SHOULD Be Logged:

**AtomicPositionManager.open_position_atomic()**:
- Line ~207: After entry order placed ✅
- Line ~241: After SL order placed ✅

### Current Logging (MISSING):

```python
# Line 207 - Entry order just placed
logger.info(f"✅ Entry order placed: {entry_order.id}")

# ❌ MISSING: Create orders table record
# ❌ MISSING: Create trades table record
```

```python
# Line 241 - SL order just placed
logger.info(f"✅ Stop-loss placed successfully")

# ❌ MISSING: Create orders table record
```

---

## 🎯 IMPLEMENTATION REQUIREMENTS

### Repository Methods Needed:

1. **`create_order(order_data: Dict) -> int`**
   - Currently: Stub (returns True, does nothing)
   - Needed: Actual implementation

2. **`create_trade(trade_data: Dict) -> int`**
   - Exists: ✅ `database/repository.py:132`
   - Status: Working, just not called

3. **`update_order(order_id: int, updates: Dict) -> bool`**
   - Currently: Does not exist
   - Needed: For order status updates

### Data Extraction Needed:

From `OrderResult` object (returned by ExchangeManager):
```python
class OrderResult:
    id: str              # ✅ Exchange order ID
    symbol: str          # ✅
    side: str            # ✅
    type: str            # ✅
    amount: Decimal      # ✅
    price: Decimal       # ✅
    filled: Decimal      # ✅
    remaining: Decimal   # ✅
    status: str          # ✅
    timestamp: datetime  # ✅
    info: Dict           # ✅ Raw exchange data
```

All required fields are available! ✅

---

## ⚠️ EDGE CASES TO HANDLE

### 1. Partial Fills
- Entry order partially filled
- Should update order record (filled, remaining)
- May need to cancel/close position if not enough filled

### 2. Order Rejection
- Exchange rejects order (insufficient margin, etc.)
- Should record order with status="REJECTED"
- Position should be marked as FAILED

### 3. Rollback Scenario
- Entry filled, SL fails
- Entry order IS logged (already executed)
- Position closed via market order
- Close order should also be logged

### 4. Duplicate Prevention
- Check if order_id already exists before insert
- Use UPSERT or check first

### 5. Fee Extraction
- Different exchanges return fees differently
- May need ExchangeResponseAdapter.extract_fee()

---

## 📋 TESTING REQUIREMENTS

### Unit Tests Needed:

1. **Test order creation** in repository
   - Insert valid order data
   - Verify record created
   - Check all fields populated

2. **Test trade creation** in repository
   - Already exists, verify still works

3. **Test order-position linking**
   - Create position
   - Create order with position_id
   - Query orders by position_id

### Integration Tests Needed:

1. **Test full position lifecycle**
   - Open position
   - Verify orders table has 2 records (entry + SL)
   - Verify trades table has 1 record (entry trade)
   - Check position.exchange_order_id matches orders.order_id

2. **Test position close**
   - Close existing position
   - Verify exit order logged
   - Verify exit trade logged

3. **Test rollback scenario**
   - Force SL failure
   - Verify entry order still logged
   - Verify position status=ROLLED_BACK

### Manual Testing:

1. Open 1 test position
2. Query orders table → expect 2 rows (entry + SL)
3. Query trades table → expect 1 row (entry trade)
4. Close position
5. Query orders table → expect 3 rows (+ close order)
6. Query trades table → expect 2 rows (+ exit trade)

---

## 🚧 CURRENT BLOCKERS

### None - Ready to Implement

All required infrastructure exists:
- ✅ Database schema correct
- ✅ create_trade() method works
- ✅ OrderResult object has all data
- ✅ position_id available in atomic flow
- ✅ exchange_order_id field in positions

Only missing: **Actual calls to create_order() and create_trade()**

---

## 📊 DATA FLOW DIAGRAM

```
┌─────────────────┐
│ Signal Received │
└────────┬────────┘
         │
         ▼
┌──────────────────────┐
│ AtomicPositionMgr    │
│ open_position_atomic │
└──────────┬───────────┘
           │
           ▼
    ┌──────────────┐
    │ CREATE       │
    │ position DB  │ → positions table
    └──────┬───────┘
           │
           ▼
    ┌──────────────────┐
    │ PLACE            │
    │ entry order      │ → Exchange API
    └──────┬───────────┘
           │
           ▼
    ┌──────────────────┐      ┌─────────────┐
    │ GET OrderResult  │      │             │
    │ from exchange    │──┬──→│ orders      │ ❌ NOT DONE
    └──────────────────┘  │   │ table       │
                          │   └─────────────┘
                          │
                          │   ┌─────────────┐
                          └──→│ trades      │ ❌ NOT DONE
                              │ table       │
                              └─────────────┘
           │
           ▼
    ┌──────────────────┐
    │ UPDATE           │
    │ position.        │ → positions table
    │ exchange_order_id│   ✅ DONE
    └──────┬───────────┘
           │
           ▼
    ┌──────────────────┐
    │ PLACE            │
    │ SL order         │ → Exchange API
    └──────┬───────────┘
           │
           ▼
    ┌──────────────────┐      ┌─────────────┐
    │ GET sl_result    │      │             │
    │ from SL manager  │─────→│ orders      │ ❌ NOT DONE
    └──────────────────┘      │ table       │
                              └─────────────┘
           │
           ▼
    ┌──────────────────┐
    │ UPDATE position  │
    │ status = ACTIVE  │ → positions table
    └──────────────────┘
```

---

## 🎯 NEXT STEPS

See: `ORDERS_TRADES_IMPLEMENTATION_PLAN.md`

---

**Report Generated**: 2025-10-16
**Investigation Status**: COMPLETE
**Ready for Implementation**: YES
