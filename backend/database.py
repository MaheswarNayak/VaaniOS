"""
Database module for VaaniOS.
Handles SQLite connection, schema initialization, and transactional queries.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
import os
import sqlite3
from typing import Any, Dict, Generator, List, Optional

# Default database file path in the backend directory
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vaanios.db")


def get_db_path() -> str:
    """Returns the current database path from environment or default."""
    return os.environ.get("VAANIOS_DB_PATH", DEFAULT_DB_PATH)


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Creates and returns a connection to the SQLite database.
    Configures row_factory to sqlite3.Row for dictionary-like column access.
    """
    target_path = db_path or get_db_path()
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db_cursor(db_path: Optional[str] = None) -> Generator[sqlite3.Cursor, None, None]:
    """Context manager that yields a cursor and safely commits and closes connection."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initializes the SQLite database with the required schema.
    Creates the 'transactions' table if it does not already exist.
    
    Table Schema:
      - id: INTEGER PRIMARY KEY AUTOINCREMENT
      - type: TEXT NOT NULL CHECK(type IN ('sale', 'expense'))
      - amount: INTEGER NOT NULL CHECK(amount > 0)
      - description: TEXT (optional)
      - timestamp: DATETIME DEFAULT CURRENT_TIMESTAMP
    """
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('sale', 'expense')),
                amount INTEGER NOT NULL CHECK(amount > 0),
                description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Create an index on timestamp and type for rapid query execution
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_timestamp 
            ON transactions(timestamp);
            """
        )


def insert_transaction(
    trans_type: str,
    amount: int,
    description: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inserts a validated transaction into the database and returns the created record.
    """
    # -------------------------------------------------------------------------
    # [GNANI AI INTEGRATION PLACEHOLDER - PRISMA (ASR)]
    # In Phase 2, audio logs, parsed voice intent metadata, and Gnani Prisma
    # session tokens can be linked or stored alongside transaction records.
    # -------------------------------------------------------------------------
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            INSERT INTO transactions (type, amount, description)
            VALUES (?, ?, ?);
            """,
            (trans_type, amount, description)
        )
        last_id = cursor.lastrowid

        cursor.execute(
            """
            SELECT id, type, amount, description, timestamp
            FROM transactions
            WHERE id = ?;
            """,
            (last_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_latest_transactions(
    limit: int = 20,
    db_path: Optional[str] = None,
    target_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetches and returns the latest transactions up to the specified limit (default: 20).
    Optionally filters by target_date (YYYY-MM-DD in local time).
    Ordered by timestamp descending, id descending.
    """
    with get_db_cursor(db_path) as cursor:
        if target_date:
            cursor.execute(
                """
                SELECT id, type, amount, description, timestamp
                FROM transactions
                WHERE DATE(timestamp, 'localtime') = DATE(?)
                ORDER BY timestamp DESC, id DESC
                LIMIT ?;
                """,
                (target_date, limit)
            )
        else:
            cursor.execute(
                """
                SELECT id, type, amount, description, timestamp
                FROM transactions
                ORDER BY timestamp DESC, id DESC
                LIMIT ?;
                """,
                (limit,)
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_summary_today(
    db_path: Optional[str] = None,
    target_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates the total sum of 'sales' and the total sum of 'expenses' for today
    or for a specific target_date (YYYY-MM-DD in local time).
    Uses SQLite's local date calculation.
    """
    with get_db_cursor(db_path) as cursor:
        if target_date:
            cursor.execute(
                """
                SELECT 
                    COALESCE(SUM(CASE WHEN type = 'sale' THEN amount ELSE 0 END), 0) AS total_sales,
                    COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS total_expenses
                FROM transactions
                WHERE DATE(timestamp, 'localtime') = DATE(?);
                """,
                (target_date,)
            )
        else:
            cursor.execute(
                """
                SELECT 
                    COALESCE(SUM(CASE WHEN type = 'sale' THEN amount ELSE 0 END), 0) AS total_sales,
                    COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS total_expenses
                FROM transactions
                WHERE DATE(timestamp, 'localtime') = DATE('now', 'localtime');
                """
            )
        row = cursor.fetchone()
        sales = row["total_sales"] if row else 0
        expenses = row["total_expenses"] if row else 0

        return {
            "sales": sales,
            "expenses": expenses,
            "net_balance": sales - expenses
        }


def get_summary_weekly(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculates total sales and total expenses grouped by day for the last 7 days
    (from 6 days ago through today in local time), filling missing days with 0.
    Returns a dictionary formatted for Chart.js consumption.
    """
    today = datetime.now().date()
    day_dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    totals_by_date: Dict[str, Dict[str, int]] = {
        d.isoformat(): {"sales": 0, "expenses": 0} for d in day_dates
    }

    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            SELECT
                DATE(timestamp, 'localtime') AS day,
                COALESCE(SUM(CASE WHEN type = 'sale' THEN amount ELSE 0 END), 0) AS total_sales,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS total_expenses
            FROM transactions
            WHERE DATE(timestamp, 'localtime') >= DATE('now', 'localtime', '-6 days')
              AND DATE(timestamp, 'localtime') <= DATE('now', 'localtime')
            GROUP BY DATE(timestamp, 'localtime')
            ORDER BY day ASC;
            """
        )
        for row in cursor.fetchall():
            day_str = row["day"]
            if day_str in totals_by_date:
                totals_by_date[day_str]["sales"] = int(row["total_sales"])
                totals_by_date[day_str]["expenses"] = int(row["total_expenses"])

    labels: List[str] = []
    dates: List[str] = []
    sales: List[int] = []
    expenses: List[int] = []
    days: List[Dict[str, Any]] = []

    for d in day_dates:
        iso = d.isoformat()
        label = d.strftime("%a")
        day_sales = totals_by_date[iso]["sales"]
        day_expenses = totals_by_date[iso]["expenses"]

        labels.append(label)
        dates.append(iso)
        sales.append(day_sales)
        expenses.append(day_expenses)
        days.append({
            "date": iso,
            "label": label,
            "sales": day_sales,
            "expenses": day_expenses,
        })

    return {
        "labels": labels,
        "dates": dates,
        "sales": sales,
        "expenses": expenses,
        "days": days,
    }


def undo_last_transaction(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Deletes the most recently inserted transaction (ordered by timestamp DESC, id DESC)
    and returns the deleted record, or None if no transactions exist.
    """
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            SELECT id, type, amount, description, timestamp
            FROM transactions
            ORDER BY timestamp DESC, id DESC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        if not row:
            return None

        deleted_record = dict(row)
        cursor.execute(
            """
            DELETE FROM transactions
            WHERE id = ?;
            """,
            (deleted_record["id"],)
        )
        return deleted_record
