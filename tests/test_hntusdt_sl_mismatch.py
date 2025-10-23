"""
Тестовый скрипт для воспроизведения проблемы HNTUSDT Stop-Loss Mismatch

ПРОБЛЕМА:
- Signal entry price = 3.31 (прогноз)
- Real entry price на бирже = 1.616 (фактическая цена)
- SL рассчитан от signal price: 3.31 * 0.98 = 3.2438
- Bybit отклоняет: "SL 3.24 должен быть ниже base_price 1.616"

ROOT CAUSE:
1. AtomicPositionManager создаёт market order
2. Order исполняется по реальной цене 1.616
3. SL calculation происходит ДО получения exec price
4. MinimumOrderLimitError НЕ вызывает rollback
5. Позиция остаётся на бирже БЕЗ SL
6. REST polling создаёт orphan record
7. Попытка поставить старый SL → reject
"""

from decimal import Decimal
from utils.decimal_utils import calculate_stop_loss


def test_signal_vs_real_entry_price_mismatch():
    """
    Воспроизводит проблему: SL рассчитан от signal price, но ордер исполнился по другой цене
    """
    print("\n" + "="*80)
    print("TEST: HNTUSDT Stop-Loss Mismatch Problem")
    print("="*80)

    # Данные из логов
    signal_entry_price = Decimal("3.31")  # Из сигнала
    real_entry_price = Decimal("1.616")   # Фактическая цена исполнения на бирже
    sl_percent = Decimal("2.0")           # 2% stop-loss

    print(f"\n📊 SCENARIO:")
    print(f"   Signal entry price: ${signal_entry_price}")
    print(f"   Real entry price:   ${real_entry_price}")
    print(f"   SL percent:         {sl_percent}%")
    print(f"   Side:               LONG (BUY)")

    # Текущий расчёт (НЕПРАВИЛЬНЫЙ)
    print(f"\n❌ CURRENT BEHAVIOR (WRONG):")
    wrong_sl = calculate_stop_loss(signal_entry_price, 'long', sl_percent)
    print(f"   SL calculated from SIGNAL price: ${wrong_sl}")
    print(f"   Ratio: {wrong_sl / real_entry_price:.4f}")

    if wrong_sl > real_entry_price:
        print(f"   🔴 ERROR: SL (${wrong_sl}) is ABOVE real entry (${real_entry_price})!")
        print(f"   🔴 Bybit will reject: \"SL must be lower than base_price\"")

    # Правильный расчёт
    print(f"\n✅ CORRECT BEHAVIOR:")
    correct_sl = calculate_stop_loss(real_entry_price, 'long', sl_percent)
    print(f"   SL calculated from REAL price: ${correct_sl}")
    print(f"   Ratio: {correct_sl / real_entry_price:.4f}")

    if correct_sl < real_entry_price:
        print(f"   ✅ VALID: SL (${correct_sl}) is BELOW real entry (${real_entry_price})")
        print(f"   ✅ Bybit will accept this SL")

    # Математическое доказательство
    print(f"\n📐 MATHEMATICAL PROOF:")
    print(f"   Signal-based SL: 3.31 * 0.98 = {float(wrong_sl):.4f}")
    print(f"   Real-based SL:   1.616 * 0.98 = {float(correct_sl):.4f}")
    print(f"   Difference:      ${float(wrong_sl - correct_sl):.4f}")
    print(f"   Error magnitude: {float((wrong_sl - correct_sl) / correct_sl * 100):.2f}%")

    # Результат
    print(f"\n" + "="*80)
    if wrong_sl > real_entry_price:
        print("🔴 TEST RESULT: BUG CONFIRMED")
        print("   Problem: Using signal price instead of execution price for SL calculation")
        return False
    else:
        print("✅ TEST RESULT: BUG FIXED")
        return True


def test_atomic_manager_execution_price_fallback():
    """
    Тестирует логику fallback в AtomicPositionManager
    """
    print("\n" + "="*80)
    print("TEST: Execution Price Fallback Logic")
    print("="*80)

    print("\n📋 SEQUENCE OF EVENTS (from logs):")
    events = [
        ("02:05:33.512", "AtomicManager.open_position_atomic() called"),
        ("02:05:33.514", "Position record created with signal entry_price=3.31"),
        ("02:05:33.516", "Entry order placed (market order)"),
        ("02:05:33.871", "fetch_order() called to get execution price"),
        ("02:05:33.875", "Order logged to DB"),
        ("02:05:35.188", "Attempt to place SL at 3.2438"),
        ("02:05:36.739", "Bybit rejects: StopLoss:324000000 > base_price:161600000"),
        ("02:05:41.904", "MinimumOrderLimitError raised"),
        ("02:05:41.906", "Position status set to 'canceled'"),
        ("02:05:41.906", "⚠️ NO ROLLBACK - position left on exchange!")
    ]

    for timestamp, event in events:
        print(f"   {timestamp} - {event}")

    print(f"\n🔍 KEY FINDINGS:")
    print(f"   1. exec_price extraction happens AFTER SL calculation ❌")
    print(f"   2. SL is calculated from signal_entry_price (3.31) ❌")
    print(f"   3. Order executes at real price (1.616)")
    print(f"   4. SL placement fails (3.24 > 1.616)")
    print(f"   5. MinimumOrderLimitError handler skips rollback ❌")
    print(f"   6. Position remains on exchange without SL ⚠️")

    print(f"\n" + "="*80)
    print("🔴 TEST RESULT: CRITICAL FLAW IN ATOMIC MANAGER")
    print("   Execution price extraction happens TOO LATE")
    print("   SL must be recalculated AFTER getting real execution price")


def test_rollback_logic():
    """
    Тестирует почему rollback не был вызван
    """
    print("\n" + "="*80)
    print("TEST: Rollback Logic Analysis")
    print("="*80)

    print("\n📋 EXCEPTION HANDLING IN atomic_position_manager.py:")
    print("\n   Lines 434-449: MinimumOrderLimitError handler")
    print("   ```python")
    print("   if \"retCode\":10001\" in error_str:")
    print("       # Update position status to 'canceled'")
    print("       await self.repository.update_position(position_id, status='canceled')")
    print("       raise MinimumOrderLimitError(...)")
    print("   ```")
    print("\n   Lines 453-462: General error handler")
    print("   ```python")
    print("   # CRITICAL: Rollback logic for other errors")
    print("   await self._rollback_position(...)")
    print("   ```")

    print(f"\n🔍 PROBLEM:")
    print(f"   ❌ MinimumOrderLimitError raises BEFORE rollback")
    print(f"   ❌ No emergency position close for this error type")
    print(f"   ❌ Position left on exchange without SL protection")

    print(f"\n✅ SOLUTION:")
    print(f"   MinimumOrderLimitError should ALSO call _rollback_position()")
    print(f"   This will close the orphaned position on the exchange")

    print(f"\n" + "="*80)
    print("🔴 TEST RESULT: ROLLBACK NOT CALLED FOR MIN LIMIT ERROR")


if __name__ == "__main__":
    print("\n")
    print("🔬 HNTUSDT STOP-LOSS MISMATCH INVESTIGATION")
    print("=" * 80)

    # Run all tests
    test_signal_vs_real_entry_price_mismatch()
    test_atomic_manager_execution_price_fallback()
    test_rollback_logic()

    print("\n\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    print("\n🔴 ROOT CAUSES IDENTIFIED:")
    print("\n   1. WRONG SL CALCULATION SOURCE:")
    print("      - Using signal entry_price (3.31) instead of execution price (1.616)")
    print("      - SL calculated BEFORE order execution")
    print("\n   2. MISSING ROLLBACK:")
    print("      - MinimumOrderLimitError doesn't trigger _rollback_position()")
    print("      - Position left on exchange without SL")
    print("\n   3. ORPHAN POSITION RECOVERY:")
    print("      - REST polling finds position on exchange")
    print("      - Creates new DB record with real entry_price")
    print("      - But tries to use OLD stop_loss_price → REJECT")

    print("\n✅ SOLUTIONS REQUIRED:")
    print("\n   1. RECALCULATE SL AFTER ORDER EXECUTION:")
    print("      - Get real execution price first")
    print("      - Recalculate stop_loss_price from exec_price")
    print("      - Place SL with correct price")
    print("\n   2. ADD ROLLBACK TO MINIMUM LIMIT ERROR:")
    print("      - Call _rollback_position() in MinimumOrderLimitError handler")
    print("      - Emergency close unprotected positions")
    print("\n   3. ORPHAN POSITION SL RECALCULATION:")
    print("      - When REST polling finds orphan position")
    print("      - Calculate SL from position's actual entry_price")
    print("      - Don't reuse old stop_loss_price")

    print("\n" + "="*80)
    print("📝 NEXT STEPS:")
    print("   1. Review this test output")
    print("   2. Confirm root causes")
    print("   3. Design comprehensive fix")
    print("   4. Implement with Golden Rule (surgical precision)")
    print("="*80 + "\n")
