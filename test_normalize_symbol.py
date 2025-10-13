#!/usr/bin/env python3
"""
Test normalize_symbol function with actual data
"""

def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format for consistent comparison
    Converts exchange format 'HIGH/USDT:USDT' to database format 'HIGHUSDT'
    """
    if '/' in symbol and ':' in symbol:
        # Exchange format: 'HIGH/USDT:USDT' -> 'HIGHUSDT'
        base_quote = symbol.split(':')[0]  # 'HIGH/USDT'
        return base_quote.replace('/', '')  # 'HIGHUSDT'
    return symbol

# Test cases from our data
print("=" * 80)
print("NORMALIZE_SYMBOL TESTING")
print("=" * 80)
print()

# Database symbols vs Exchange symbols
test_pairs = [
    ("FORTHUSDT", "FORTH/USDT:USDT"),
    ("NILUSDT", "NIL/USDT:USDT"),
    ("XVSUSDT", "XVS/USDT:USDT"),
    ("LISTAUSDT", "LISTA/USDT:USDT"),
    ("STGUSDT", "STG/USDT:USDT"),
    ("TOKENUSDT", "TOKEN/USDT:USDT"),
]

print("Testing symbol normalization:")
print()

all_ok = True
for db_symbol, exchange_symbol in test_pairs:
    normalized_db = normalize_symbol(db_symbol)
    normalized_exchange = normalize_symbol(exchange_symbol)

    match = "✅ MATCH" if normalized_db == normalized_exchange else "❌ MISMATCH"

    print(f"DB: {db_symbol:<20} → {normalized_db:<15}")
    print(f"EX: {exchange_symbol:<20} → {normalized_exchange:<15}")
    print(f"    {match}")
    print()

    if normalized_db != normalized_exchange:
        all_ok = False

if all_ok:
    print("=" * 80)
    print("✅ ALL SYMBOLS NORMALIZE CORRECTLY")
    print("=" * 80)
    print()
    print("CONCLUSION:")
    print("normalize_symbol() works correctly.")
    print("The problem is NOT with symbol normalization.")
    print()
else:
    print("=" * 80)
    print("❌ SYMBOL NORMALIZATION FAILED")
    print("=" * 80)
    print()
    print("This would explain why verify_position_exists() returns False!")
    print()
