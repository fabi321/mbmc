import pickle
import sqlite3
import threading
from pathlib import Path
from typing import Callable, TypeVar
import inspect

from mbmc.util import CACHE_DIR

CACHE_FILE: Path = CACHE_DIR / " cache.db"

local = threading.local()


def init_db():
    """Initialize the cache database for the current thread."""
    if not hasattr(local, "cache"):
        local.cache = sqlite3.connect(CACHE_FILE)
    local.cache.executescript("""
    create table if not exists cache (
        name text not null,
        input_value text not null,
        last_access text not null default (unixepoch()),
        value blob,
        unique(name, input_value) on conflict replace
    ) strict;
    create unique index if not exists idx_name_input on cache (name, input_value);
    delete from cache where last_access < unixepoch() - 604800;
    """)
    local.cache.commit()


T = TypeVar("T", bound=Callable)


def cached(func: T) -> T:
    """Decorator to cache function results in a SQLite database."""

    def wrapper(*args):
        if not hasattr(local, "cache"):
            local.cache = sqlite3.connect(CACHE_FILE)
        name = f"{func.__module__}.{func.__qualname__}"
        if '.' in func.__qualname__ and not isinstance(func, staticmethod):
            input_value = repr(args[1:])  # skip 'self' or 'cls'
        else:
            input_value = repr(args)
        cursor = local.cache.execute(
            "select rowid, value from cache where name = ? and input_value = ?",
            (name, input_value),
        )
        row = cursor.fetchone()
        if row:
            local.cache.execute(
                "update cache set last_access = unixepoch() where rowid = ?",
                (row[0],),
            )
            local.cache.commit()
            return pickle.loads(row[1])
        result = func(*args)
        local.cache.execute(
            "insert into cache (name, input_value, value) values (?, ?, ?)",
            (name, input_value, pickle.dumps(result)),
        )
        local.cache.commit()
        return result

    return wrapper


init_db()
