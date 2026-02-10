"""
Canonical symbol normalization for the entire project.

Replaces 4 duplicate definitions across:
- core/exchange_manager.py
- core/position_manager.py
- core/position_synchronizer.py
- websocket/binance_hybrid_stream.py
"""


def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format for consistent comparison.

    Converts exchange format 'HIGH/USDT:USDT' to database format 'HIGHUSDT'.
    Handles empty strings and already-normalized symbols.

    Args:
        symbol: Symbol in any format

    Returns:
        Normalized symbol (e.g., 'HIGHUSDT')

    Examples:
        >>> normalize_symbol('BTC/USDT:USDT')
        'BTCUSDT'
        >>> normalize_symbol('BTCUSDT')
        'BTCUSDT'
        >>> normalize_symbol('')
        ''
    """
    if not symbol:
        return ""
    if ':' in symbol:
        symbol = symbol.split(':')[0]
    return symbol.replace('/', '').upper()
