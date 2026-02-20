from __future__ import annotations

import json
from typing import Any, Iterable


def _rows_to_dicts(cursor, rows) -> list[dict[str, Any]]:
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in rows]


def fetch_one(conn, sql: str, params: Iterable[Any]) -> dict[str, Any] | None:
    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    row = cur.fetchone()
    if row is None:
        return None
    return _rows_to_dicts(cur, [row])[0]


def fetch_all(conn, sql: str, params: Iterable[Any]) -> list[dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    return _rows_to_dicts(cur, rows)


def loads_json(value: Any, *, default):
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default
