from typing import Any

from travel_agent.tools.db import TravelDatabase
from travel_agent.tools.groups import get_full_group_profile


DEFAULT_MIN_RATING = 7.5


def calculate_hotel_total_price(
    hotel: dict[str, Any],
    nights: int,
) -> int:
    """
    Calculates total hotel stay price.

    @param hotel Hotel row dictionary.
    @param nights Number of hotel nights.
    @return Total hotel price in rubles.
    """
    return int(hotel["price_per_night_rub"]) * nights


def search_hotels(
    destination: str | None = None,
    nights: int | None = None,
    max_total_price_rub: int | None = None,
    breakfast_required: bool | None = None,
    free_cancellation_required: bool | None = None,
    min_stars: int | None = None,
    min_rating: float | None = DEFAULT_MIN_RATING,
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Searches hotels using hard constraints.

    This function applies strict filters only. Preference-based ordering is
    handled by rank_hotels.

    @param destination Optional destination code.
    @param nights Optional number of hotel nights.
    @param max_total_price_rub Optional maximum total hotel price.
    @param breakfast_required If True, only hotels with breakfast are returned.
    @param free_cancellation_required If True, only hotels with free cancellation are returned.
    @param min_stars Optional minimum hotel class.
    @param min_rating Optional minimum hotel rating.
    @param db Optional database wrapper.
    @return List of hotel candidates.
    """
    db = db or TravelDatabase()

    query = """
        SELECT
            hotel_id,
            destination,
            stars,
            price_per_night_rub,
            breakfast_included,
            free_cancellation,
            rating,
            notes
        FROM hotels
        WHERE 1 = 1
    """
    params: list[Any] = []

    if destination is not None:
        query += " AND destination = ?"
        params.append(destination)

    if breakfast_required is True:
        query += " AND breakfast_included = 1"

    if free_cancellation_required is True:
        query += " AND free_cancellation = 1"

    if min_stars is not None:
        query += " AND stars >= ?"
        params.append(min_stars)

    if min_rating is not None:
        query += " AND rating >= ?"
        params.append(min_rating)

    query += """
        ORDER BY
            rating DESC,
            stars DESC,
            price_per_night_rub ASC
    """

    hotels = db.fetch_all(query, tuple(params))

    enriched_hotels = []

    for hotel in hotels:
        enriched_hotel = dict(hotel)

        if nights is not None:
            total_price = calculate_hotel_total_price(enriched_hotel, nights)
            enriched_hotel["nights"] = nights
            enriched_hotel["total_price_rub"] = total_price

            if max_total_price_rub is not None and total_price > max_total_price_rub:
                continue

        enriched_hotels.append(enriched_hotel)

    return enriched_hotels


def score_hotel(hotel: dict[str, Any]) -> int:
    """
    Calculates a simple ranking score for a hotel.

    Lower score is better. Price is the base factor. Higher rating, breakfast,
    free cancellation and higher hotel class improve the score.

    @param hotel Hotel row dictionary.
    @return Integer score.
    """
    score = int(hotel["price_per_night_rub"])

    score -= int(float(hotel["rating"]) * 1_000)
    score -= int(hotel["stars"]) * 1_500

    if int(hotel["breakfast_included"]) == 1:
        score -= 3_000
    else:
        score += 5_000

    if int(hotel["free_cancellation"]) == 1:
        score -= 2_000

    notes = str(hotel.get("notes") or "").lower()

    if "семей" in notes or "family" in notes:
        score -= 2_000

    if "пляж" in notes or "beach" in notes:
        score -= 1_500

    if "центр" in notes:
        score -= 1_000

    if "шум" in notes:
        score += 3_000

    return score


def rank_hotels(hotels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sorts hotel candidates by planning score.

    @param hotels List of hotel dictionaries.
    @return Ranked list of hotels with an additional ranking_score field.
    """
    ranked_hotels = []

    for hotel in hotels:
        ranked_hotel = dict(hotel)
        ranked_hotel["ranking_score"] = score_hotel(hotel)
        ranked_hotels.append(ranked_hotel)

    return sorted(
        ranked_hotels,
        key=lambda hotel: (
            hotel["ranking_score"],
            hotel.get("total_price_rub", hotel["price_per_night_rub"]),
            -float(hotel["rating"]),
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


def infer_hotel_constraints_from_group(
    group_profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Infers hotel search constraints from group profile and preferences.

    The function extracts strict hotel constraints from group comments,
    traveler notes and structured preferences.

    @param group_profile Full group profile returned by get_full_group_profile.
    @return Dictionary with hotel search constraints.
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

    breakfast_required = _text_contains_any(
        combined_text,
        ["завтрак", "breakfast", "meal"],
    )

    free_cancellation_required = _text_contains_any(
        combined_text,
        ["бесплатная отмена", "free cancellation", "отмена"],
    )

    min_stars = None

    if _text_contains_any(
        combined_text,
        ["5*", "5plus", "hotel_class 5", "только отель 5"],
    ):
        min_stars = 5
    elif _text_contains_any(
        combined_text,
        ["4*", "4plus", "4+", "4*+", "hotel_class"],
    ):
        min_stars = 4

    return {
        "destination": group["destination"],
        "nights": summary["nights"],
        "breakfast_required": breakfast_required,
        "free_cancellation_required": free_cancellation_required,
        "min_stars": min_stars,
        "min_rating": DEFAULT_MIN_RATING,
    }


def search_hotels_for_group(
    group_id: str,
    max_total_price_rub: int | None = None,
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Searches and ranks hotels for a travel group.

    The function loads group context, infers hotel constraints and returns
    ranked hotel candidates for the group's destination.

    @param group_id Group identifier.
    @param max_total_price_rub Optional maximum total hotel budget.
    @param db Optional database wrapper.
    @return Ranked list of hotel candidates.
    """
    db = db or TravelDatabase()

    group_profile = get_full_group_profile(group_id, db)
    constraints = infer_hotel_constraints_from_group(group_profile)

    candidates = search_hotels(
        destination=constraints["destination"],
        nights=constraints["nights"],
        max_total_price_rub=max_total_price_rub,
        breakfast_required=constraints["breakfast_required"],
        free_cancellation_required=constraints["free_cancellation_required"],
        min_stars=constraints["min_stars"],
        min_rating=constraints["min_rating"],
        db=db,
    )

    return rank_hotels(candidates)


def get_hotel_by_id(
    hotel_id: str,
    db: TravelDatabase | None = None,
) -> dict[str, Any] | None:
    """
    Returns one hotel by hotel_id.

    @param hotel_id Hotel identifier.
    @param db Optional database wrapper.
    @return Hotel row dictionary or None.
    """
    db = db or TravelDatabase()

    return db.fetch_one(
        """
        SELECT
            hotel_id,
            destination,
            stars,
            price_per_night_rub,
            breakfast_included,
            free_cancellation,
            rating,
            notes
        FROM hotels
        WHERE hotel_id = ?
        """,
        (hotel_id,),
    )