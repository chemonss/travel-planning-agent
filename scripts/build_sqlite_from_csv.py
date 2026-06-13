import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data" / "travelers"
OUTPUT_DB_PATH = DATA_DIR / "travelers.sqlite"


CSV_TO_TABLE = {
    "travelers.csv": "travelers",
    "traveler_preferences.csv": "traveler_preferences",
    "travel_groups.csv": "travel_groups",
    "group_members.csv": "group_members",
    "flights.csv": "flights",
    "hotels.csv": "hotels",
    "tours.csv": "tours",
}


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalizes CSV column names before writing the table to SQLite.
    """
    df = df.copy()
    df.columns = [
        column.strip().lower().replace(" ", "_").replace("-", "_")
        for column in df.columns
    ]
    return df


def load_csv_to_table(conn: sqlite3.Connection, csv_path: Path, table_name: str) -> None:
    """
    Loads one CSV file into one SQLite table.

    @param conn Active SQLite connection.
    @param csv_path Path to the source CSV file.
    @param table_name Target SQLite table name.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    print(f"[INFO] Loading {csv_path.name} -> {table_name}")

    df = pd.read_csv(csv_path)
    df = normalize_column_names(df)

    df.to_sql(table_name, conn, if_exists="replace", index=False)

    print(f"[OK] Table '{table_name}' created with {len(df)} rows")


def create_indexes(conn: sqlite3.Connection) -> None:
    """
    Creates useful SQLite indexes for agent tools.
    """
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_travelers_traveler_id ON travelers(traveler_id)",
        "CREATE INDEX IF NOT EXISTS idx_preferences_traveler_id ON traveler_preferences(traveler_id)",

        "CREATE INDEX IF NOT EXISTS idx_groups_group_id ON travel_groups(group_id)",
        "CREATE INDEX IF NOT EXISTS idx_group_members_group_id ON group_members(group_id)",
        "CREATE INDEX IF NOT EXISTS idx_group_members_traveler_id ON group_members(traveler_id)",

        "CREATE INDEX IF NOT EXISTS idx_flights_flight_id ON flights(flight_id)",
        "CREATE INDEX IF NOT EXISTS idx_flights_destination ON flights(destination)",

        "CREATE INDEX IF NOT EXISTS idx_hotels_hotel_id ON hotels(hotel_id)",
        "CREATE INDEX IF NOT EXISTS idx_hotels_destination ON hotels(destination)",

        "CREATE INDEX IF NOT EXISTS idx_tours_tour_id ON tours(tour_id)",
        "CREATE INDEX IF NOT EXISTS idx_tours_destination ON tours(destination)",
    ]

    for statement in index_statements:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as error:
            print(f"[WARNING] Could not create index:")
            print(f"          {statement}")
            print(f"          Reason: {error}")


def main() -> None:
    """
    Builds data/travelers/travelers.sqlite from CSV files.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_DB_PATH.exists():
        print(f"[INFO] Removing old database: {OUTPUT_DB_PATH}")
        OUTPUT_DB_PATH.unlink()

    with sqlite3.connect(OUTPUT_DB_PATH) as conn:
        for csv_filename, table_name in CSV_TO_TABLE.items():
            csv_path = DATA_DIR / csv_filename
            load_csv_to_table(conn, csv_path, table_name)

        create_indexes(conn)
        conn.commit()

    print(f"\n[DONE] SQLite database created:")
    print(OUTPUT_DB_PATH)


if __name__ == "__main__":
    main()