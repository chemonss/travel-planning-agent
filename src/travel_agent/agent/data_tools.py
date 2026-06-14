from typing import Any

from travel_agent.rag.retriever import retrieve_policy_context
from travel_agent.tools.groups import get_full_group_profile
from travel_agent.tools.trip_options import get_trip_options_for_group
from travel_agent.tools.flights import search_flights_for_group
from travel_agent.tools.hotels import search_hotels_for_group
from travel_agent.tools.tours import (
    get_tour_by_id,
    compare_tour_vs_independent,
    search_tours_for_group,
)


def get_group_profile_tool(group_id: str) -> dict[str, Any]:
    """
    Returns full group profile by group_id.
    """
    return get_full_group_profile(group_id)


def get_trip_options_tool(group_id: str) -> dict[str, Any]:
    """
    Returns full trip options for a group.
    """
    return get_trip_options_for_group(group_id)


def search_flights_tool(group_id: str) -> list[dict[str, Any]]:
    """
    Returns ranked flight candidates for a group.
    """
    return search_flights_for_group(group_id)


def search_hotels_tool(group_id: str) -> list[dict[str, Any]]:
    """
    Returns ranked hotel candidates for a group.
    """
    return search_hotels_for_group(group_id)


def search_tours_tool(group_id: str) -> list[dict[str, Any]]:
    """
    Returns ranked package tour candidates for a group.
    """
    return search_tours_for_group(group_id)


def compare_tour_with_independent_tool(
    group_id: str,
    tour_id: str,
) -> dict[str, Any]:
    """
    Compares a selected package tour with the best independent option.
    """
    trip_options = get_trip_options_for_group(group_id)

    tour = get_tour_by_id(tour_id)
    flight = trip_options["best"]["flight"]
    hotel = trip_options["best"]["hotel"]

    if tour is None:
        return {
            "can_compare": False,
            "reason": f"Unknown tour_id: {tour_id}",
        }

    return compare_tour_vs_independent(
        tour=tour,
        flight=flight,
        hotel=hotel,
    )


def retrieve_policy_context_tool(
    query: str,
    top_k: int = 4,
) -> dict[str, Any]:
    """
    Retrieves policy context from markdown documents.

    The agent should use this tool before answering info, planning,
    replanning, clarification, rejection or escalation questions.

    @param query User request or internal policy question.
    @param top_k Number of policy chunks to retrieve.
    @return Retrieved chunks and formatted context.
    """
    return retrieve_policy_context(
        query=query,
        top_k=top_k,
    )