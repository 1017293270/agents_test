from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from app.models import ColumnInfo, MySqlConnection, SchemaInspectResponse, TableInfo


def connect_mysql(connection: MySqlConnection):
    return pymysql.connect(
        host=connection.host,
        port=connection.port,
        user=connection.user,
        password=connection.password,
        database=connection.database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=connection.connect_timeout,
        read_timeout=60,
        write_timeout=60,
        autocommit=True,
    )


def test_connection(connection: MySqlConnection) -> str:
    with connect_mysql(connection) as db:
        with db.cursor() as cursor:
            cursor.execute("select 1 as ok")
            cursor.fetchone()
    return "MySQL connection ok"


def inspect_schema(connection: MySqlConnection, sample_rows: int = 3) -> SchemaInspectResponse:
    with connect_mysql(connection) as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                select table_name as table_name, table_comment as table_comment
                from information_schema.tables
                where table_schema = %s and table_type = 'BASE TABLE'
                order by table_name
                """,
                (connection.database,),
            )
            table_rows = cursor.fetchall()

            cursor.execute(
                """
                select
                    table_name as table_name,
                    column_name as column_name,
                    column_type as column_type,
                    is_nullable as is_nullable,
                    column_key as column_key,
                    column_comment as column_comment
                from information_schema.columns
                where table_schema = %s
                order by table_name, ordinal_position
                """,
                (connection.database,),
            )
            column_rows = cursor.fetchall()

            columns_by_table: dict[str, list[ColumnInfo]] = {}
            for row in column_rows:
                table_name = row_get(row, "table_name")
                columns_by_table.setdefault(table_name, []).append(
                    ColumnInfo(
                        name=row_get(row, "column_name"),
                        type=row_get(row, "column_type"),
                        nullable=row_get(row, "is_nullable") == "YES",
                        key=row_get(row, "column_key") or None,
                        comment=row_get(row, "column_comment") or None,
                    )
                )

            tables: list[TableInfo] = []
            for table in table_rows:
                name = row_get(table, "table_name")
                columns = columns_by_table.get(name, [])
                samples = _sample_table(cursor, connection.database, name, columns, sample_rows)
                tables.append(
                    TableInfo(
                        name=name,
                        comment=row_get(table, "table_comment") or None,
                        columns=columns,
                        samples=samples,
                    )
                )

    return SchemaInspectResponse(database=connection.database, tables=tables)


def execute_select(connection: MySqlConnection, sql: str, timeout_seconds: int = 30) -> tuple[list[dict[str, Any]], int]:
    with connect_mysql(connection) as db:
        with db.cursor() as cursor:
            try:
                cursor.execute("set session max_execution_time=%s", (timeout_seconds * 1000,))
            except Exception:
                pass
            cursor.execute(sql)
            rows = [_json_safe_row(row) for row in cursor.fetchall()]
    return rows, len(rows)


def _sample_table(
    cursor,
    database: str,
    table: str,
    columns: Iterable[ColumnInfo],
    sample_rows: int,
) -> list[dict[str, Any]]:
    if sample_rows <= 0:
        return []
    column_names = [column.name for column in columns][:12]
    if not column_names:
        return []

    select_columns = ", ".join(_quote_identifier(column) for column in column_names)
    sql = f"select {select_columns} from {_quote_identifier(database)}.{_quote_identifier(table)} limit %s"
    try:
        cursor.execute(sql, (sample_rows,))
        return [_json_safe_row(row) for row in cursor.fetchall()]
    except Exception:
        return []


def _quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def row_get(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row[key]
    upper_key = key.upper()
    if upper_key in row:
        return row[upper_key]
    lower_map = {str(row_key).lower(): row_key for row_key in row}
    mapped_key = lower_map.get(key.lower())
    if mapped_key is not None:
        return row[mapped_key]
    raise KeyError(key)


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(value) for key, value in row.items()}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
