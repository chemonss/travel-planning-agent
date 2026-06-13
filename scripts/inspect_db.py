import sqlite3
from pathlib import Path


DB_PATH = Path("data/travelers/travelers.sqlite")


def main() -> None:
    """
    Prints SQLite database tables and their column schemas.

    This script is used as the first inspection step before implementing
    database tools for the travel-planning agent.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    print("Tables:")
    for table in tables:
        print(f"\n=== {table} ===")

        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()

        for column in columns:
            cid, name, col_type, not_null, default_value, pk = column
            print(
                f"{name}: {col_type}, "
                f"not_null={bool(not_null)}, "
                f"default={default_value}, "
                f"pk={bool(pk)}"
            )

        cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
        rows = cursor.fetchall()
        print("Sample rows:")
        for row in rows:
            print(row)

    conn.close()


if __name__ == "__main__":
    main()