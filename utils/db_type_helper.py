"""
PostgreSQL Type Helper for Safe Type Casting
Prevents asyncpg.exceptions.UndefinedFunctionError
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class PostgreSQLTypeHelper:
    """
    Helper for safe type casting in PostgreSQL queries
    Prevents type mismatch errors like "character varying = integer"
    """

    @staticmethod
    def safe_cast_param(value: Any, target_type: str) -> Any:
        """
        Safely cast a parameter to the target PostgreSQL type

        Args:
            value: Value to cast
            target_type: Target PostgreSQL type ('integer', 'varchar', 'timestamp', etc)

        Returns:
            Properly typed value for PostgreSQL
        """
        if value is None:
            return None

        try:
            if target_type in ('integer', 'int', 'int4', 'int8', 'bigint'):
                return int(value) if value is not None else None

            elif target_type in ('varchar', 'text', 'character varying'):
                return str(value)

            elif target_type in ('timestamp', 'timestamptz', 'timestamp with time zone'):
                if isinstance(value, str):
                    # Remove timezone info for PostgreSQL
                    value = value.replace('+00:00', '').replace('Z', '')
                    return datetime.fromisoformat(value)
                elif isinstance(value, (int, float)):
                    return datetime.fromtimestamp(value)
                return value

            elif target_type in ('boolean', 'bool'):
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 't')
                return bool(value)

            elif target_type in ('numeric', 'decimal', 'float', 'double precision', 'real'):
                if target_type in ('numeric', 'decimal'):
                    return Decimal(str(value))
                return float(value)

            elif target_type == 'json' or target_type == 'jsonb':
                import json
                if isinstance(value, str):
                    return json.loads(value)
                return value

            else:
                logger.debug(f"Unknown type {target_type}, returning value as-is")
                return value

        except (ValueError, TypeError) as e:
            logger.error(f"Failed to cast {value} to {target_type}: {e}")
            return value

    @staticmethod
    def build_safe_query(base_query: str, params_with_types: List[Tuple[Any, str]]) -> Tuple[str, List]:
        """
        Build a query with properly typed parameters

        Args:
            base_query: SQL query with $1, $2, etc placeholders
            params_with_types: List of (value, postgresql_type) tuples

        Returns:
            Tuple of (query, converted_params)

        Example:
            query = "SELECT * FROM users WHERE id = $1 AND status = $2"
            params = [(123, 'integer'), ('active', 'varchar')]
            query, safe_params = PostgreSQLTypeHelper.build_safe_query(query, params)
        """
        converted_params = []

        for value, param_type in params_with_types:
            converted = PostgreSQLTypeHelper.safe_cast_param(value, param_type)
            converted_params.append(converted)

        logger.debug(f"Converted params: {converted_params}")
        return base_query, converted_params

    @staticmethod
    def add_type_casts_to_query(query: str, cast_mappings: dict) -> str:
        """
        Add explicit type casts to a query

        Args:
            query: Original SQL query
            cast_mappings: Dict of {column: type} to cast

        Returns:
            Query with explicit type casts added

        Example:
            query = "SELECT * FROM table WHERE id = $1"
            mappings = {'id': 'integer'}
            # Returns: "SELECT * FROM table WHERE id::integer = $1"
        """
        modified_query = query

        for column, cast_type in cast_mappings.items():
            # Add ::type casting to column references
            # This handles patterns like "column = " or "column IN"
            patterns = [
                (f"{column} =", f"{column}::{cast_type} ="),
                (f"{column} IN", f"{column}::{cast_type} IN"),
                (f"{column} >", f"{column}::{cast_type} >"),
                (f"{column} <", f"{column}::{cast_type} <"),
                (f"{column} >=", f"{column}::{cast_type} >="),
                (f"{column} <=", f"{column}::{cast_type} <="),
                (f"{column} !=", f"{column}::{cast_type} !="),
                (f"{column} <>", f"{column}::{cast_type} <>"),
            ]

            for old_pattern, new_pattern in patterns:
                if old_pattern in modified_query and f"{column}::" not in modified_query:
                    modified_query = modified_query.replace(old_pattern, new_pattern)

        return modified_query

    @staticmethod
    async def diagnose_type_mismatch(conn, query: str, params: List) -> dict:
        """
        Diagnose type mismatches in a failed query

        Args:
            conn: AsyncPG connection
            query: SQL query that failed
            params: Parameters passed to the query

        Returns:
            Dict with diagnostic information
        """
        diagnosis = {
            'query': query,
            'params': params,
            'param_types': [type(p).__name__ for p in params],
            'recommendations': []
        }

        # Extract table names from query (basic extraction)
        import re
        table_pattern = r'FROM\s+(\w+\.?\w+)'
        tables = re.findall(table_pattern, query, re.IGNORECASE)

        for table in tables:
            # Get column types for each table
            schema_query = """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = $1 OR table_schema || '.' || table_name = $1
                ORDER BY ordinal_position;
            """

            try:
                columns = await conn.fetch(schema_query, table)
                diagnosis[f'table_{table}'] = [
                    {'column': row['column_name'], 'type': row['data_type']}
                    for row in columns
                ]
            except Exception as e:
                logger.error(f"Failed to get schema for {table}: {e}")

        # Add recommendations based on common patterns
        if "character varying = integer" in str(diagnosis.get('error', '')):
            diagnosis['recommendations'].append(
                "Add explicit type casting: column::integer or column::varchar"
            )

        return diagnosis


# Convenience function for signal processor
def fix_signal_query_types(query: str) -> str:
    """
    Fix common type issues in signal processing queries

    Args:
        query: Original SQL query

    Returns:
        Query with type casts added
    """
    cast_mappings = {
        'trading_pair_id': 'integer',
        'exchange_id': 'integer',
        'signal_id': 'varchar',
        'status': 'varchar',
        'user_id': 'integer'
    }

    # Add explicit casts for known problematic columns
    fixed_query = query

    # Fix JOIN conditions
    if "trading_pair_id = tp.id" in fixed_query:
        fixed_query = fixed_query.replace(
            "trading_pair_id = tp.id",
            "trading_pair_id::integer = tp.id"
        )

    # Fix exchange_id comparisons
    if "exchange_id = 1" in fixed_query:
        fixed_query = fixed_query.replace(
            "exchange_id = 1",
            "exchange_id::integer = 1"
        )
    if "exchange_id = 2" in fixed_query:
        fixed_query = fixed_query.replace(
            "exchange_id = 2",
            "exchange_id::integer = 2"
        )

    # Fix signal_id comparisons
    if "signal_id = sc.id" in fixed_query:
        fixed_query = fixed_query.replace(
            "signal_id = sc.id",
            "signal_id = sc.id::varchar"
        )

    return fixed_query