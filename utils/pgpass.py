"""
PostgreSQL .pgpass file reader utility

Provides functionality to read passwords from ~/.pgpass file,
following PostgreSQL standard format and wildcard matching.
"""
import os
from pathlib import Path
from typing import Optional


def read_pgpass(host: str, port: int, database: str, user: str) -> str:
    """Read password from .pgpass file

    Format: hostname:port:database:username:password
    Wildcards (*) are supported for any field except password

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user

    Returns:
        Password string if found, empty string otherwise
    """
    pgpass_path = Path.home() / '.pgpass'

    if not pgpass_path.exists():
        return ''

    try:
        with open(pgpass_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split(':')
                if len(parts) != 5:
                    continue

                p_host, p_port, p_db, p_user, p_pass = parts

                # Match with wildcards
                if (p_host in ('*', host) and
                    p_port in ('*', str(port)) and
                    p_db in ('*', database) and
                    p_user in ('*', user)):
                    return p_pass
    except Exception:
        pass

    return ''


def get_db_password() -> str:
    """Get database password from environment or .pgpass file

    First checks DB_PASSWORD environment variable.
    If not set or empty, reads from .pgpass file using DB_HOST, DB_PORT,
    DB_NAME, and DB_USER environment variables.

    Returns:
        Password string
    """
    password = os.getenv('DB_PASSWORD', '')

    if not password:
        host = os.getenv('DB_HOST', 'localhost')
        port = int(os.getenv('DB_PORT', 5432))
        database = os.getenv('DB_NAME', 'tradingbot_db')
        user = os.getenv('DB_USER', 'tradingbot')
        password = read_pgpass(host, port, database, user)

    return password


def build_db_url() -> str:
    """Build PostgreSQL connection URL with password from .pgpass if needed

    Returns:
        PostgreSQL connection URL string
    """
    host = os.getenv('DB_HOST', 'localhost')
    port = int(os.getenv('DB_PORT', 5432))
    database = os.getenv('DB_NAME', 'tradingbot_db')
    user = os.getenv('DB_USER', 'tradingbot')
    password = get_db_password()

    return f'postgresql://{user}:{password}@{host}:{port}/{database}'
