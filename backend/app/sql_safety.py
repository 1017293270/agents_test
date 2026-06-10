import re

import sqlglot
from sqlglot import expressions as exp


class SqlSafetyError(ValueError):
    pass


_DANGEROUS_PATTERNS = [
    r"\binto\s+outfile\b",
    r"\binto\s+dumpfile\b",
    r"\bfor\s+update\b",
    r"\block\s+in\s+share\s+mode\b",
    r"/\*!",
]


def validate_select_sql(sql: str, default_limit: int = 500) -> str:
    normalized = sql.strip().rstrip(";").strip()
    if not normalized:
        raise SqlSafetyError("SQL is empty")

    statements = sqlglot.parse(normalized, dialect="mysql")
    if len(statements) != 1:
        raise SqlSafetyError("SQL must be a single SELECT statement")

    expression = statements[0]
    if not isinstance(expression, exp.Select):
        raise SqlSafetyError("Only SELECT statements are allowed")

    lowered = normalized.lower()
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            raise SqlSafetyError("SQL contains a disallowed read modifier")

    if ";" in normalized:
        raise SqlSafetyError("SQL must be a single SELECT statement")

    if expression.args.get("limit") is None:
        expression.set("limit", exp.Limit(expression=exp.Literal.number(default_limit)))
        return expression.sql(dialect="mysql")

    return normalized
