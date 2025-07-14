import os
import sqlite3
from wf.utils.log import get_logger

logger = get_logger(__name__)

def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Get a SQLite connection with foreign-keys enabled
    and rows returned as sqlite3.Row.
    """
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path: str) -> sqlite3.Connection:
    """
    Initialize (or migrate) the database by running the
    DDL in schema.sql, then return a live connection.
    """
    conn = get_connection(db_path)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    logger.info("Initializing DB schema: %s", schema_path)
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn