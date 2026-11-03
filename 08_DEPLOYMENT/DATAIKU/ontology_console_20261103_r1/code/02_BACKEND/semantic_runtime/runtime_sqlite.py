"""Route only explicit Oracle runtime record identifiers to the memory adapter."""
from sqlite3 import *
import sqlite3 as _sqlite


def connect(database, *args, **kwargs):
    from .oracle_runtime_paths import virtual
    if virtual(database):
        from .oracle_record_sqlite import connect as oracle_connect
        return oracle_connect(database, *args, **kwargs)
    return _sqlite.connect(database, *args, **kwargs)
