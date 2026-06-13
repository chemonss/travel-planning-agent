import csv
import sys
from pathlib import Path
from typing import Any

from travel_agent.tools.flights import search_flights_for_group
from travel_agent.tools.hotels import search_hotels_for_group


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FLIGHT_REFERENCE_PATH = PROJECT_ROOT / "data" / "reference" / "flight_recommendations.csv"
HOTEL_REFERENCE_PATH = PROJECT_ROOT / "data" / "reference" / "hotel_recommendations.csv"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """
    Reads a CSV file into a list of dictionaries.

    @param path Path to the CSV file.
    @return List of CSV rows.
    @raises FileNotFoundError If the file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Reference file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def get_first_existing_value(
    row: dict[str, str],
    possible_keys: list[str],
) -> str | None:
    """
    Returns the first non-empty value from possible CSV columns.

    This makes the script robust to slightly different reference column names.

    @param row CSV row dictionary.
    @param possible_keys Possible column names.
    @return First non-empty value or None.
    """
    for key in possible_keys:
        value = row.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    return None


def is_empty_expected_value(value: str | None) -> bool:
    """
    Checks whether an expected reference value is empty.

    @param value Reference value.
    @return True if the value should be treated as missing.
    """
    if value is None:
        return True

    normalized = value.strip().lower()

    return normalized in {"", "none", "null", "nan", "-", "n/a"}


def check_flight_recommendations() -> tuple[int, int]:
    """
    Compares ranked flight tools with flight reference recommendations.

    @return Tuple with passed count and total checked count.
    """
    rows = read_csv_rows(FLIGHT_REFERENCE_PATH)

    passed = 0
    total = 0

    print("\n=== Flight recommendations ===")

    for row in rows:
        group_id = get_first_existing_value(row, ["group_id"])
        expected_flight_id = get_first_existing_value(
            row,
            ["recommended_flight_id", "flight_id", "expected_flight_id"],
        )
        expected_status = get_first_existing_value(
            row,
            ["status", "expected_status"],
        )

        if group_id is None:
            print("[SKIP] Row without group_id")
            continue

        if is_empty_expected_value(expected_flight_id):
            print(
                f"[SKIP] {group_id}: no expected flight id"
                + (f", status={expected_status}" if expected_status else "")
            )
            continue

        total += 1

        try:
            candidates = search_flights_for_group(group_id)
            actual_flight_id = candidates[0]["flight_id"] if candidates else None
        except Exception as error:
            actual_flight_id = None
            print(f"[ERROR] {group_id}: {error}")

        if actual_flight_id == expected_flight_id:
            passed += 1
            print(f"[OK]   {group_id}: expected {expected_flight_id}, got {actual_flight_id}")
        else:
            print(f"[FAIL] {group_id}: expected {expected_flight_id}, got {actual_flight_id}")

    return passed, total


def check_hotel_recommendations() -> tuple[int, int]:
    """
    Compares ranked hotel tools with hotel reference recommendations.

    @return Tuple with passed count and total checked count.
    """
    rows = read_csv_rows(HOTEL_REFERENCE_PATH)

    passed = 0
    total = 0

    print("\n=== Hotel recommendations ===")

    for row in rows:
        group_id = get_first_existing_value(row, ["group_id"])
        expected_hotel_id = get_first_existing_value(
            row,
            ["recommended_hotel_id", "hotel_id", "expected_hotel_id"],
        )
        expected_status = get_first_existing_value(
            row,
            ["status", "expected_status"],
        )

        if group_id is None:
            print("[SKIP] Row without group_id")
            continue

        if is_empty_expected_value(expected_hotel_id):
            print(
                f"[SKIP] {group_id}: no expected hotel id"
                + (f", status={expected_status}" if expected_status else "")
            )
            continue

        total += 1

        try:
            candidates = search_hotels_for_group(group_id)
            actual_hotel_id = candidates[0]["hotel_id"] if candidates else None
        except Exception as error:
            actual_hotel_id = None
            print(f"[ERROR] {group_id}: {error}")

        if actual_hotel_id == expected_hotel_id:
            passed += 1
            print(f"[OK]   {group_id}: expected {expected_hotel_id}, got {actual_hotel_id}")
        else:
            print(f"[FAIL] {group_id}: expected {expected_hotel_id}, got {actual_hotel_id}")

    return passed, total


def print_summary(
    flight_result: tuple[int, int],
    hotel_result: tuple[int, int],
) -> None:
    """
    Prints final reference-check summary.

    @param flight_result Passed and total count for flight checks.
    @param hotel_result Passed and total count for hotel checks.
    """
    flight_passed, flight_total = flight_result
    hotel_passed, hotel_total = hotel_result

    total_passed = flight_passed + hotel_passed
    total_checked = flight_total + hotel_total

    print("\n=== Summary ===")
    print(f"Flights: {flight_passed}/{flight_total}")
    print(f"Hotels:  {hotel_passed}/{hotel_total}")
    print(f"Total:   {total_passed}/{total_checked}")


def main() -> int:
    """
    Runs reference recommendation checks.

    @return Process exit code: 0 if all checked cases passed, otherwise 1.
    """
    flight_result = check_flight_recommendations()
    hotel_result = check_hotel_recommendations()

    print_summary(flight_result, hotel_result)

    total_passed = flight_result[0] + hotel_result[0]
    total_checked = flight_result[1] + hotel_result[1]

    if total_checked == 0:
        print("\n[WARNING] No reference rows were checked.")
        return 1

    if total_passed != total_checked:
        print("\n[FAIL] Some recommendations do not match reference files.")
        return 1

    print("\n[OK] All checked recommendations match reference files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())