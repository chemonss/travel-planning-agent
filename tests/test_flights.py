from travel_agent.tools.flights import (
    is_early_departure,
    is_night_arrival,
    search_flights,
    search_flights_for_group,
)


def test_is_early_departure() -> None:
    """
    Checks early departure detection.
    """
    assert is_early_departure("05:50") is True
    assert is_early_departure("07:00") is False
    assert is_early_departure("10:20") is False


def test_is_night_arrival() -> None:
    """
    Checks night arrival detection.
    """
    assert is_night_arrival("22:59") is False
    assert is_night_arrival("23:00") is True
    assert is_night_arrival("23:30") is True


def test_search_flights_istanbul_with_baggage() -> None:
    """
    Checks strict flight search for Istanbul with included baggage.
    """
    flights = search_flights(
        origin_city="Moscow",
        destination="IST",
        baggage_required=True,
        avoid_early_departure=True,
        avoid_night_arrival=True,
    )

    flight_ids = {flight["flight_id"] for flight in flights}

    assert "FL-102" in flight_ids
    assert "FL-118" not in flight_ids


def test_search_flights_for_group_g0001() -> None:
    """
    Checks ranked flight search for family Istanbul scenario.
    """
    flights = search_flights_for_group("G-0001")

    assert len(flights) > 0
    assert flights[0]["flight_id"] == "FL-102"


def test_search_flights_for_group_g0003() -> None:
    """
    Checks ranked flight search for Bangkok baggage scenario.
    """
    flights = search_flights_for_group("G-0003")

    assert len(flights) > 0
    assert flights[0]["flight_id"] == "FL-311"