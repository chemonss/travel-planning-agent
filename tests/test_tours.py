from travel_agent.tools.hotels import search_hotels_for_group
from travel_agent.tools.flights import search_flights_for_group
from travel_agent.tools.tours import (
    compare_tour_vs_independent,
    enrich_tour_with_hotel,
    get_tour_by_id,
    search_tours_for_group,
)


def test_get_tour_by_id() -> None:
    """
    Checks tour lookup by identifier.
    """
    tour = get_tour_by_id("TR-020")

    assert tour is not None
    assert tour["tour_id"] == "TR-020"
    assert tour["destination"] == "DXB"
    assert tour["hotel_id"] == "HT-101"


def test_enrich_tour_with_hotel() -> None:
    """
    Checks that linked hotel data is added to a tour.
    """
    tour = get_tour_by_id("TR-020")
    assert tour is not None

    enriched_tour = enrich_tour_with_hotel(tour)

    assert enriched_tour["hotel"] is not None
    assert enriched_tour["hotel"]["hotel_id"] == "HT-101"


def test_search_tours_for_group_g0002() -> None:
    """
    Checks package tour search for Dubai scenario.
    """
    tours = search_tours_for_group("G-0002")

    assert len(tours) > 0
    assert tours[0]["tour_id"] == "TR-020"
    assert tours[0]["hotel"]["hotel_id"] == "HT-101"


def test_compare_tour_vs_independent() -> None:
    """
    Checks package tour comparison with independent booking.
    """
    tours = search_tours_for_group("G-0002")
    flights = search_flights_for_group("G-0002")
    hotels = search_hotels_for_group("G-0002")

    comparison = compare_tour_vs_independent(
        tour=tours[0],
        flight=flights[0],
        hotel=hotels[0],
    )

    assert comparison["can_compare"] is True
    assert comparison["tour_total_price_rub"] == tours[0]["total_price_rub"]
    assert comparison["independent_total_price_rub"] == (
        flights[0]["price_rub"] + hotels[0]["total_price_rub"]
    )
    assert "tour_is_reasonable" in comparison