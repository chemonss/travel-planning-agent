from typing import Any

from travel_agent.tools.db import TravelDatabase
from travel_agent.tools.groups import get_full_group_profile
from travel_agent.tools.hotels import get_hotel_by_id


def get_tour_by_id(
    tour_id: str,
    db: TravelDatabase | None = None,
) -> dict[str, Any] | None:
    """
    Returns one package tour by tour_id.

    @param tour_id Tour identifier.
    @param db Optional database wrapper.
    @return Tour row dictionary or None.
    """
    db = db or TravelDatabase()

    return db.fetch_one(
        """
        SELECT
            tour_id,
            destination,
            total_price_rub,
            includes_flight,
            includes_transfer,
            hotel_id,
            notes
        FROM tours
        WHERE tour_id = ?
        """,
        (tour_id,),
    )


def search_tours(
    destination: str | None = None,
    max_total_price_rub: int | None = None,
    require_flight: bool = True,
    require_transfer: bool = False,
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Searches package tours using hard constraints.

    @param destination Optional destination code.
    @param max_total_price_rub Optional maximum total tour price.
    @param require_flight If True, only tours including flight are returned.
    @param require_transfer If True, only tours including transfer are returned.
    @param db Optional database wrapper.
    @return List of tour candidates.
    """
    db = db or TravelDatabase()

    query = """
        SELECT
            tour_id,
            destination,
            total_price_rub,
            includes_flight,
            includes_transfer,
            hotel_id,
            notes
        FROM tours
        WHERE 1 = 1
    """
    params: list[Any] = []

    if destination is not None:
        query += " AND destination = ?"
        params.append(destination)

    if max_total_price_rub is not None:
        query += " AND total_price_rub <= ?"
        params.append(max_total_price_rub)

    if require_flight:
        query += " AND includes_flight = 1"

    if require_transfer:
        query += " AND includes_transfer = 1"

    query += """
        ORDER BY
            total_price_rub ASC
    """

    return db.fetch_all(query, tuple(params))


def enrich_tour_with_hotel(
    tour: dict[str, Any],
    db: TravelDatabase | None = None,
) -> dict[str, Any]:
    """
    Adds linked hotel data to a package tour.

    @param tour Tour row dictionary.
    @param db Optional database wrapper.
    @return Tour dictionary with a nested hotel object.
    """
    db = db or TravelDatabase()

    enriched_tour = dict(tour)
    hotel_id = enriched_tour.get("hotel_id")

    enriched_tour["hotel"] = get_hotel_by_id(hotel_id, db) if hotel_id else None

    return enriched_tour


def enrich_tours_with_hotels(
    tours: list[dict[str, Any]],
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Adds linked hotel data to all package tours.

    @param tours List of tour dictionaries.
    @param db Optional database wrapper.
    @return List of enriched tour dictionaries.
    """
    db = db or TravelDatabase()

    return [enrich_tour_with_hotel(tour, db) for tour in tours]


def score_tour(tour: dict[str, Any]) -> int:
    """
    Calculates a simple ranking score for a package tour.

    Lower score is better. The tour price is the base factor. Included
    transfer, good linked hotel rating and package convenience improve score.

    @param tour Tour row dictionary, optionally enriched with hotel data.
    @return Integer score.
    """
    score = int(tour["total_price_rub"])

    if int(tour["includes_flight"]) == 1:
        score -= 5_000
    else:
        score += 50_000

    if int(tour["includes_transfer"]) == 1:
        score -= 7_000

    hotel = tour.get("hotel")

    if hotel is not None:
        score -= int(float(hotel["rating"]) * 1_000)
        score -= int(hotel["stars"]) * 1_000

        if int(hotel["breakfast_included"]) == 1:
            score -= 2_000

        if int(hotel["free_cancellation"]) == 1:
            score -= 1_500

    notes = str(tour.get("notes") or "").lower()

    if "ручная проверка" in notes:
        score += 100_000

    if "пляж" in notes:
        score -= 2_000

    if "бюджет" in notes:
        score -= 1_000

    return score


def rank_tours(tours: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sorts package tours by planning score.

    @param tours List of tour dictionaries.
    @return Ranked list of tours with an additional ranking_score field.
    """
    ranked_tours = []

    for tour in tours:
        ranked_tour = dict(tour)
        ranked_tour["ranking_score"] = score_tour(tour)
        ranked_tours.append(ranked_tour)

    return sorted(
        ranked_tours,
        key=lambda tour: (
            tour["ranking_score"],
            tour["total_price_rub"],
        ),
    )


def compare_tour_vs_independent(
    tour: dict[str, Any],
    flight: dict[str, Any] | None,
    hotel: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Compares package tour price with independent flight and hotel booking.

    A package tour is considered economically reasonable if it is not more
    than 10 percent more expensive than independent booking.

    @param tour Package tour dictionary.
    @param flight Selected flight dictionary.
    @param hotel Selected hotel dictionary with total_price_rub field.
    @return Comparison dictionary.
    """
    if flight is None or hotel is None:
        return {
            "can_compare": False,
            "independent_total_price_rub": None,
            "tour_total_price_rub": int(tour["total_price_rub"]),
            "price_difference_rub": None,
            "tour_price_ratio": None,
            "tour_is_reasonable": False,
            "reason": "Cannot compare tour without selected flight and hotel.",
        }

    independent_total = int(flight["price_rub"]) + int(hotel["total_price_rub"])
    tour_total = int(tour["total_price_rub"])

    if independent_total <= 0:
        ratio = None
        tour_is_reasonable = False
    else:
        ratio = tour_total / independent_total
        tour_is_reasonable = ratio <= 1.10

    return {
        "can_compare": True,
        "independent_total_price_rub": independent_total,
        "tour_total_price_rub": tour_total,
        "price_difference_rub": tour_total - independent_total,
        "tour_price_ratio": ratio,
        "tour_is_reasonable": tour_is_reasonable,
        "reason": (
            "Tour is within 10 percent of independent booking."
            if tour_is_reasonable
            else "Tour is more than 10 percent more expensive than independent booking."
        ),
    }


def search_tours_for_group(
    group_id: str,
    max_total_price_rub: int | None = None,
    require_transfer: bool = False,
    db: TravelDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    Searches and ranks package tours for a travel group.

    The function uses the group's destination and budget by default.

    @param group_id Group identifier.
    @param max_total_price_rub Optional maximum total tour price.
    @param require_transfer If True, only tours with included transfer are returned.
    @param db Optional database wrapper.
    @return Ranked list of enriched package tours.
    """
    db = db or TravelDatabase()

    group_profile = get_full_group_profile(group_id, db)
    group = group_profile["group"]

    budget_limit = max_total_price_rub

    if budget_limit is None:
        budget_limit = int(group["budget_rub"])

    candidates = search_tours(
        destination=group["destination"],
        max_total_price_rub=budget_limit,
        require_flight=True,
        require_transfer=require_transfer,
        db=db,
    )

    enriched_candidates = enrich_tours_with_hotels(candidates, db)

    return rank_tours(enriched_candidates)