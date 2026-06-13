from datetime import date
from typing import Any

from travel_agent.tools.db import TravelDatabase


def get_group(
    group_id: str,
    db: TravelDatabase | None = None,
) -> dict[str, Any] | None:
    """
    Returns one travel group by group_id.

    @param group_id Group identifier, for example "G-0001".
    @param db Optional database wrapper.
    @return Group row as dictionary or None.
    """
    db = db or TravelDatabase()

    return db.fetch_one(
        """
        SELECT
            group_id,
            origin_city,
            destination,
            start_date,
            end_date,
            budget_rub,
            group_comment
        FROM travel_groups
        WHERE group_id = ?
        """,
        (group_id,),
    )


def get_group_members(
    group_id: str,
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Returns all travelers belonging to a travel group.

    The result includes both membership role and traveler profile fields.

    @param group_id Group identifier.
    @param db Optional database wrapper.
    @return List of group member dictionaries.
    """
    db = db or TravelDatabase()

    return db.fetch_all(
        """
        SELECT
            gm.group_id,
            gm.traveler_id,
            gm.role_in_group,
            t.full_name,
            t.age,
            t.citizenship,
            t.home_airport,
            t.loyalty_program,
            t.notes
        FROM group_members AS gm
        JOIN travelers AS t
            ON gm.traveler_id = t.traveler_id
        WHERE gm.group_id = ?
        ORDER BY gm.traveler_id
        """,
        (group_id,),
    )


def get_group_preferences(
    group_id: str,
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Returns all structured preferences for all travelers in a group.

    @param group_id Group identifier.
    @param db Optional database wrapper.
    @return List of preference dictionaries.
    """
    db = db or TravelDatabase()

    return db.fetch_all(
        """
        SELECT
            gm.group_id,
            gm.traveler_id,
            tp.preference_type,
            tp.preference_value,
            tp.comment
        FROM group_members AS gm
        JOIN traveler_preferences AS tp
            ON gm.traveler_id = tp.traveler_id
        WHERE gm.group_id = ?
        ORDER BY gm.traveler_id, tp.preference_type
        """,
        (group_id,),
    )


def calculate_nights(start_date: str, end_date: str) -> int:
    """
    Calculates number of hotel nights between two ISO dates.

    @param start_date Trip start date in YYYY-MM-DD format.
    @param end_date Trip end date in YYYY-MM-DD format.
    @return Number of nights.
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    return (end - start).days


def get_full_group_profile(
    group_id: str,
    db: TravelDatabase | None = None,
) -> dict[str, Any]:
    """
    Returns full group context required by the planning agent.

    The result combines group parameters, members, structured preferences,
    number of travelers, child presence and trip duration.

    @param group_id Group identifier.
    @param db Optional database wrapper.
    @return Full group profile dictionary.
    @raises ValueError If group_id is unknown.
    """
    db = db or TravelDatabase()

    group = get_group(group_id, db)

    if group is None:
        raise ValueError(f"Unknown group_id: {group_id}")

    members = get_group_members(group_id, db)
    preferences = get_group_preferences(group_id, db)

    nights = calculate_nights(
        start_date=group["start_date"],
        end_date=group["end_date"],
    )

    has_children = any(member["age"] < 18 for member in members)

    return {
        "group": group,
        "members": members,
        "preferences": preferences,
        "summary": {
            "group_id": group_id,
            "origin_city": group["origin_city"],
            "destination": group["destination"],
            "start_date": group["start_date"],
            "end_date": group["end_date"],
            "nights": nights,
            "budget_rub": group["budget_rub"],
            "traveler_count": len(members),
            "has_children": has_children,
        },
    }