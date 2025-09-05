from .connection import get_cursor

def fetch_all(sql, params=()):
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()

def fetch_one(sql, params=()):
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()

def execute(sql, params=()):
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount