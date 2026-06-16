import sqlite3
from pathlib import Path
from typing import Any


# Якорим путь к БД на корень проекта, чтобы tools работали из любого cwd.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "travelers" / "travelers.sqlite"


class TravelDatabase:
    """
    Read-only SQLite wrapper for the travel-planning agent.

    This class provides a safe interface for SELECT queries and returns
    SQLite rows as dictionaries.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

    def fetch_one(
        self,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        """
        Executes a SELECT query and returns one row.

        @param query SQL SELECT query.
        @param params SQL query parameters.
        @return Row as dictionary or None.
        """
        rows = self.fetch_all(query, params)
        return rows[0] if rows else None

    def fetch_all(
        self,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        """
        Executes a SELECT query and returns all rows.

        @param query SQL SELECT query.
        @param params SQL query parameters.
        @return List of rows as dictionaries.
        """
        if not query.strip().lower().startswith("select"):
            raise ValueError("Only SELECT queries are allowed.")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [dict(row) for row in rows]