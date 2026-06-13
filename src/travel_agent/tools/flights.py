from datetime import time
from typing import Any

from travel_agent.tools.db import TravelDatabase
from travel_agent.tools.groups import get_full_group_profile


EARLY_DEPARTURE_LIMIT = "07:00"
NIGHT_ARRIVAL_LIMIT = "23:00"


def _parse_time(value: str) -> time:
    """
    Parses HH:MM time string into a time object.

    @param value Time string in HH:MM format.
    @return Parsed time object.
    """
    hours, minutes = value.split(":")
    return time(hour=int(hours), minute=int(minutes))


def is_early_departure(departure_time: str) -> bool:
    """
    Checks whether a flight departure is considered too early.

    A departure before 07:00 is treated as early for planning purposes.

    @param departure_time Departure time in HH:MM format.
    @return True if departure is before the early-departure threshold.
    """
    return _parse_time(departure_time) < _parse_time(EARLY_DEPARTURE_LIMIT)


def is_night_arrival(arrival_time: str) -> bool:
    """
    Checks whether a flight arrival is considered a night arrival.

    An arrival at or after 23:00 is treated as night arrival.

    @param arrival_time Arrival time in HH:MM format.
    @return True if arrival is at or after the night-arrival threshold.
    """
    return _parse_time(arrival_time) >= _parse_time(NIGHT_ARRIVAL_LIMIT)


def search_flights(
    origin_city: str | None = None,
    destination: str | None = None,
    max_price_rub: int | None = None,
    baggage_required: bool | None = None,
    direct_only: bool = False,
    avoid_early_departure: bool = False,
    avoid_night_arrival: bool = False,
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Searches flights using hard constraints.

    This function only applies strict filters. Preference-based ordering is
    handled separately by rank_flights.

    @param origin_city Optional origin city.
    @param destination Optional destination code.
    @param max_price_rub Optional maximum flight price.
    @param baggage_required If True, only flights with included baggage are returned.
    @param direct_only If True, only flights without stops are returned.
    @param avoid_early_departure If True, departures before 07:00 are excluded.
    @param avoid_night_arrival If True, arrivals at or after 23:00 are excluded.
    @param db Optional database wrapper.
    @return List of flight candidates.
    """
    db = db or TravelDatabase()

    query = """
        SELECT
            flight_id,
            origin_city,
            destination,
            price_rub,
            baggage_included,
            stops,
            departure_time,
            arrival_time,
            fare_type,
            notes
        FROM flights
        WHERE 1 = 1
    """
    params: list[Any] = []

    if origin_city is not None:
        query += " AND origin_city = ?"
        params.append(origin_city)

    if destination is not None:
        query += " AND destination = ?"
        params.append(destination)

    if max_price_rub is not None:
        query += " AND price_rub <= ?"
        params.append(max_price_rub)

    if baggage_required is True:
        query += " AND baggage_included = 1"

    if direct_only is True:
        query += " AND stops = 0"

    if avoid_early_departure is True:
        query += " AND departure_time >= ?"
        params.append(EARLY_DEPARTURE_LIMIT)

    if avoid_night_arrival is True:
        query += " AND arrival_time < ?"
        params.append(NIGHT_ARRIVAL_LIMIT)

    query += """
        ORDER BY
            price_rub ASC,
            stops ASC,
            departure_time ASC
    """

    return db.fetch_all(query, tuple(params))


def score_flight(
    flight: dict[str, Any],
    budget_sensitive: bool = False,
) -> int:
    """
    Calculates a ranking score for a flight.

    Lower score is better. The score balances price and comfort. If the group
    is budget-sensitive, cheaper flights and flights marked as budget-compatible
    are preferred more strongly.

    @param flight Flight row dictionary.
    @param budget_sensitive Whether budget constraints should dominate comfort.
    @return Integer score.
    """
    score = int(flight["price_rub"])

    baggage_included = int(flight["baggage_included"])
    stops = int(flight["stops"])
    fare_type = str(flight["fare_type"]).lower()
    notes = str(flight.get("notes") or "").lower()

    if baggage_included == 0:
        score += 20_000

    if budget_sensitive:
        score += stops * 4_000
    else:
        score += stops * 10_000

    if is_early_departure(flight["departure_time"]):
        score += 15_000

    if is_night_arrival(flight["arrival_time"]):
        score += 30_000

    if fare_type == "basic":
        score += 5_000
    elif fare_type == "comfort" and not budget_sensitive:
        score -= 3_000

    if budget_sensitive:
        if "под бюджет" in notes or "бюджет" in notes or "лимит" in notes:
            score -= 12_000

        if "дороже" in notes:
            score += 10_000

    return score


def rank_flights(
    flights: list[dict[str, Any]],
    budget_sensitive: bool = False,
) -> list[dict[str, Any]]:
    """
    Sorts flight candidates by planning score.

    @param flights List of flight dictionaries.
    @param budget_sensitive Whether budget constraints should dominate comfort.
    @return Ranked list of flights with an additional ranking_score field.
    """
    ranked_flights = []

    for flight in flights:
        ranked_flight = dict(flight)
        ranked_flight["ranking_score"] = score_flight(
            flight,
            budget_sensitive=budget_sensitive,
        )
        ranked_flights.append(ranked_flight)

    return sorted(
        ranked_flights,
        key=lambda flight: (
            flight["ranking_score"],
            flight["price_rub"],
            flight["stops"],
        ),
    )


def _text_contains_any(text: str | None, keywords: list[str]) -> bool:
    """
    Checks whether text contains at least one keyword.

    @param text Source text.
    @param keywords Keywords to search for.
    @return True if at least one keyword is present.
    """
    if not text:
        return False

    lowered_text = text.lower()

    return any(keyword.lower() in lowered_text for keyword in keywords)


def infer_flight_constraints_from_group(
    group_profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Infers flight search constraints from group profile and preferences.

    The function extracts hard and soft constraints from group comments,
    traveler notes and structured preferences.

    @param group_profile Full group profile returned by get_full_group_profile.
    @return Dictionary with flight search constraints.
    """
    group = group_profile["group"]
    members = group_profile["members"]
    preferences = group_profile["preferences"]
    summary = group_profile["summary"]

    all_text_parts = [group.get("group_comment")]

    for member in members:
        all_text_parts.append(member.get("notes"))

    for preference in preferences:
        all_text_parts.append(preference.get("comment"))
        all_text_parts.append(preference.get("preference_type"))
        all_text_parts.append(preference.get("preference_value"))

    combined_text = " ".join(part for part in all_text_parts if part)

    baggage_required = _text_contains_any(
        combined_text,
        ["багаж", "baggage"],
    )

    avoid_night_arrival = summary["has_children"] or _text_contains_any(
        combined_text,
        ["ночн", "night"],
    )

    avoid_early_departure = _text_contains_any(
        combined_text,
        ["ранн", "до 06:00", "до 07:00", "early"],
    )

    direct_only = _text_contains_any(
        combined_text,
        ["только прямой", "прямой рейс", "direct only"],
    )

    budget_sensitive = _text_contains_any(
        combined_text,
        ["бюджет", "лимит", "сниж", "дешевле", "budget"],
    )   

    return {
        "origin_city": group["origin_city"],
        "destination": group["destination"],
        "baggage_required": baggage_required,
        "avoid_night_arrival": avoid_night_arrival,
        "avoid_early_departure": avoid_early_departure,
        "direct_only": direct_only,
        "budget_sensitive": budget_sensitive,
    }


def search_flights_for_group(
    group_id: str,
    max_price_rub: int | None = None,
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Searches and ranks flights for a travel group.

    The function loads group context, infers flight constraints and returns
    ranked flight candidates for the group's origin city and destination.

    @param group_id Group identifier.
    @param max_price_rub Optional maximum flight price.
    @param db Optional database wrapper.
    @return Ranked list of flight candidates.
    """
    db = db or TravelDatabase()

    group_profile = get_full_group_profile(group_id, db)
    constraints = infer_flight_constraints_from_group(group_profile)

    candidates = search_flights(
        origin_city=constraints["origin_city"],
        destination=constraints["destination"],
        max_price_rub=max_price_rub,
        baggage_required=constraints["baggage_required"],
        direct_only=constraints["direct_only"],
        avoid_early_departure=constraints["avoid_early_departure"],
        avoid_night_arrival=constraints["avoid_night_arrival"],
        db=db,
    )

    return rank_flights(
        candidates,
        budget_sensitive=constraints["budget_sensitive"],
    )