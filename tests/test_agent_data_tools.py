from travel_agent.agent.data_tools import (
    compare_tour_with_independent_tool,
    get_group_profile_tool,
    get_trip_options_tool,
    retrieve_policy_context_tool,
    search_flights_tool,
    search_hotels_tool,
    search_tours_tool,
)


def test_get_group_profile_tool() -> None:
    """
    Checks group profile agent-facing tool.
    """
    profile = get_group_profile_tool("G-0001")

    assert profile["summary"]["group_id"] == "G-0001"
    assert profile["summary"]["destination"] == "IST"
    assert profile["summary"]["traveler_count"] == 3


def test_get_trip_options_tool() -> None:
    """
    Checks main trip options agent-facing tool.
    """
    result = get_trip_options_tool("G-0001")

    assert result["best"]["flight"]["flight_id"] == "FL-102"
    assert result["best"]["hotel"]["hotel_id"] == "HT-045"
    assert result["recommended_option"] is not None


def test_search_flights_tool() -> None:
    """
    Checks flight search agent-facing tool.
    """
    flights = search_flights_tool("G-0003")

    assert len(flights) > 0
    assert flights[0]["flight_id"] == "FL-311"


def test_search_hotels_tool() -> None:
    """
    Checks hotel search agent-facing tool.
    """
    hotels = search_hotels_tool("G-0002")

    assert len(hotels) > 0
    assert hotels[0]["hotel_id"] == "HT-101"


def test_search_tours_tool() -> None:
    """
    Checks package tour search agent-facing tool.
    """
    tours = search_tours_tool("G-0002")

    assert len(tours) > 0
    assert tours[0]["tour_id"] == "TR-020"


def test_compare_tour_with_independent_tool() -> None:
    """
    Checks package tour comparison agent-facing tool.
    """
    comparison = compare_tour_with_independent_tool(
        group_id="G-0002",
        tour_id="TR-020",
    )

    assert comparison["can_compare"] is True
    assert comparison["tour_total_price_rub"] == 214700
    assert comparison["tour_is_reasonable"] is True


def test_retrieve_policy_context_tool() -> None:
    """
    Checks policy retrieval agent-facing tool.
    """
    result = retrieve_policy_context_tool(
        query="Что считается ночным прилётом?",
        top_k=3,
    )

    assert result["query"] == "Что считается ночным прилётом?"
    assert len(result["chunks"]) > 0
    assert result["context"] != "No relevant policy context found."