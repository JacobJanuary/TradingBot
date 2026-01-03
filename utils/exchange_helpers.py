"""
Exchange ID mapping helpers

Converts between:
- exchange_name: str ('binance')
- exchange_id: int (1)

Used for:
- Reading params from monitoring.params (requires exchange_id)
- Storing positions in monitoring.positions (uses exchange_name)
"""

def exchange_name_to_id(name: str) -> int:
    """
    Convert exchange name to exchange_id for monitoring.params

    Args:
        name: Exchange name ('binance', 'bybit', case-insensitive)

    Returns:
        int: Exchange ID (1=Binance, 2=Bybit)

    Raises:
        ValueError: If exchange name is unknown

    Examples:
        >>> exchange_name_to_id('binance')
        1
        >>> exchange_name_to_id('Bybit')
        2
    """
    name_lower = name.lower().strip()

    if name_lower == 'binance':
        return 1
    else:
        raise ValueError(
            f"Unknown exchange name: '{name}'. "
            f"Expected 'binance'"
        )


def exchange_id_to_name(exchange_id: int) -> str:
    """
    Convert exchange_id to exchange name

    Args:
        exchange_id: Exchange ID (1 or 2)

    Returns:
        str: Exchange name ('binance' or 'bybit')

    Raises:
        ValueError: If exchange_id is unknown

    Examples:
        >>> exchange_id_to_name(1)
        'binance'
        >>> exchange_id_to_name(2)
        'bybit'
    """
    if exchange_id == 1:
        return 'binance'
    else:
        raise ValueError(
            f"Unknown exchange_id: {exchange_id}. "
            f"Expected 1 (Binance)"
        )
