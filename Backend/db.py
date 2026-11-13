"""Thin raw-SQL access layer on top of psycopg2 (no ORM)."""
from contextlib import contextmanager

from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

import config

_pool = None


def init_pool():
    global _pool
    _pool = ThreadedConnectionPool(
        1,
        10,
        **config.DB,
        # Safety net: this app only ever reads, and no query may run longer than 30 s.
        options="-c default_transaction_read_only=on -c statement_timeout=30000",
    )


def close_pool():
    if _pool is not None:
        _pool.closeall()


@contextmanager
def _connection():
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        conn.rollback()  # read-only app: always end the transaction cleanly
        _pool.putconn(conn)


def fetch_all(query, params=None):
    with _connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def fetch_value(query, params=None):
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return row[0] if row else None


def render_sql(query, params=None):
    """Return the final SQL text with parameters filled in (for display/debugging only)."""
    with _connection() as conn:
        with conn.cursor() as cur:
            return cur.mogrify(query, params).decode()


def load_schema_info():
    """
    Read the real columns of every configured layer from information_schema.
    For text columns with few distinct values (e.g. fclass) the values are
    collected too, so the LLM can map "hospital" to fclass = 'hospital'.
    """
    info = {}
    for layer, meta in config.LAYERS.items():
        rows = fetch_all(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (config.DB_SCHEMA, layer),
        )
        if not rows:
            raise RuntimeError(f"Table {config.DB_SCHEMA}.{layer} was not found in the database")

        columns = []
        for r in rows:
            name, dtype = r["column_name"], r["data_type"]
            low = name.lower()
            if low.startswith("shape") or low in config.IGNORED_COLUMNS:
                continue
            entry = {"name": name, "type": dtype, "values": None}
            if dtype in config.TEXT_TYPES:
                query = sql.SQL(
                    "SELECT DISTINCT {col} AS v FROM {schema}.{table} "
                    "WHERE {col} IS NOT NULL ORDER BY 1 LIMIT %s"
                ).format(
                    col=sql.Identifier(name),
                    schema=sql.Identifier(config.DB_SCHEMA),
                    table=sql.Identifier(layer),
                )
                vals = [v["v"] for v in fetch_all(query, (config.MAX_CATEGORY_VALUES + 1,)) if v["v"]]
                if 0 < len(vals) <= config.MAX_CATEGORY_VALUES:
                    entry["values"] = vals
            columns.append(entry)

        info[layer] = {
            "geometry": meta["geometry"],
            "description": meta["description"],
            "columns": columns,
        }
    return info
