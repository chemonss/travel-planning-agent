from typing import Any

from travel_agent.tools.budget import (
    build_independent_budget_summary,
    build_package_budget_summary,
)
from travel_agent.tools.db import TravelDatabase
from travel_agent.tools.flights import search_flights_for_group
from travel_agent.tools.groups import get_full_group_profile
from travel_agent.tools.hotels import search_hotels_for_group
from travel_agent.tools.tours import (
    compare_tour_vs_independent,
    search_tours_for_group,
)


def get_best_candidate(
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Returns the first candidate from a ranked candidate list.

    @param candidates Ranked list of candidate dictionaries.
    @return Best candidate or None if the list is empty.
    """
    if not candidates:
        return None

    return candidates[0]


def build_independent_option(
    flight: dict[str, Any] | None,
    hotel: dict[str, Any] | None,
    budget_rub: int,
) -> dict[str, Any]:
    """
    Builds a structured independent flight plus hotel option.

    @param flight Selected flight dictionary.
    @param hotel Selected hotel dictionary.
    @param budget_rub Group budget in rubles.
    @return Independent option dictionary.
    """
    budget_summary = build_independent_budget_summary(
        flight=flight,
        hotel=hotel,
        budget_rub=budget_rub,
    )

    return {
        "available": flight is not None and hotel is not None,
        "option_type": "independent",
        "flight": flight,
        "hotel": hotel,
        "budget": budget_summary,
    }


def build_package_option(
    tour: dict[str, Any] | None,
    flight: dict[str, Any] | None,
    hotel: dict[str, Any] | None,
    budget_rub: int,
) -> dict[str, Any]:
    """
    Builds a structured package tour option.

    @param tour Selected package tour dictionary.
    @param flight Best independent flight for comparison.
    @param hotel Best independent hotel for comparison.
    @param budget_rub Group budget in rubles.
    @return Package option dictionary.
    """
    budget_summary = build_package_budget_summary(
        tour=tour,
        budget_rub=budget_rub,
    )

    comparison = None

    if tour is not None:
        comparison = compare_tour_vs_independent(
            tour=tour,
            flight=flight,
            hotel=hotel,
        )

    return {
        "available": tour is not None,
        "option_type": "package",
        "tour": tour,
        "budget": budget_summary,
        "comparison_with_independent": comparison,
    }


def select_recommended_option(
    independent_option: dict[str, Any],
    package_option: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Selects the preferred option between independent and package booking.

    Package tour is preferred if it is available, fits budget and is not more
    than 10 percent more expensive than independent booking. Otherwise the
    independent option is preferred if it fits the budget.

    @param independent_option Structured independent option.
    @param package_option Structured package option.
    @return Recommended option dictionary or None.
    """
    package_available = package_option["available"]
    package_budget_ok = package_option["budget"]["budget_ok"]
    comparison = package_option["comparison_with_independent"]

    if (
        package_available
        and package_budget_ok is True
        and comparison is not None
        and comparison["tour_is_reasonable"] is True
    ):
        return package_option

    independent_available = independent_option["available"]
    independent_budget_ok = independent_option["budget"]["budget_ok"]

    if independent_available and independent_budget_ok is True:
        return independent_option

    if package_available and package_budget_ok is True:
        return package_option

    return None


def get_trip_options_for_group(
    group_id: str,
    db: TravelDatabase | None = None,
) -> dict[str, Any]:
    """
    Builds complete trip options for a travel group.

    The function combines group profile, ranked flight candidates, ranked hotel
    candidates, ranked package tour candidates, budget summaries and a selected
    recommended option.

    @param group_id Group identifier.
    @param db Optional database wrapper.
    @return Structured trip options dictionary.
    """
    db = db or TravelDatabase()

    group_profile = get_full_group_profile(group_id, db)
    budget_rub = int(group_profile["summary"]["budget_rub"])

    flight_candidates = search_flights_for_group(group_id, db=db)
    hotel_candidates = search_hotels_for_group(group_id, db=db)
    tour_candidates = search_tours_for_group(group_id, db=db)

    best_flight = get_best_candidate(flight_candidates)
    best_hotel = get_best_candidate(hotel_candidates)
    best_tour = get_best_candidate(tour_candidates)

    independent_option = build_independent_option(
        flight=best_flight,
        hotel=best_hotel,
        budget_rub=budget_rub,
    )

    package_option = build_package_option(
        tour=best_tour,
        flight=best_flight,
        hotel=best_hotel,
        budget_rub=budget_rub,
    )

    recommended_option = select_recommended_option(
        independent_option=independent_option,
        package_option=package_option,
    )

    return {
        "group_profile": group_profile,
        "candidates": {
            "flights": flight_candidates,
            "hotels": hotel_candidates,
            "tours": tour_candidates,
        },
        "best": {
            "flight": best_flight,
            "hotel": best_hotel,
            "tour": best_tour,
        },
        "options": {
            "independent": independent_option,
            "package": package_option,
        },
        "recommended_option": recommended_option,
    }