from travel_agent.tools.hotels import (
    calculate_hotel_total_price,
    get_hotel_by_id,
    search_hotels,
    search_hotels_for_group,
)


def test_calculate_hotel_total_price() -> None:
    """
    Checks hotel total price calculation.
    """
    hotel = {
        "price_per_night_rub": 11260,
    }

    assert calculate_hotel_total_price(hotel, nights=5) == 56300


def test_get_hotel_by_id() -> None:
    """
    Checks hotel lookup by identifier.
    """
    hotel = get_hotel_by_id("HT-045")

    assert hotel is not None
    assert hotel["hotel_id"] == "HT-045"
    assert hotel["destination"] == "IST"


def test_search_hotels_istanbul_with_breakfast() -> None:
    """
    Checks strict hotel search for Istanbul with breakfast.
    """
    hotels = search_hotels(
        destination="IST",
        nights=5,
        breakfast_required=True,
        min_stars=4,
    )

    hotel_ids = {hotel["hotel_id"] for hotel in hotels}

    assert "HT-045" in hotel_ids
    assert "HT-052" not in hotel_ids


def test_search_hotels_for_group_g0001() -> None:
    """
    Checks ranked hotel search for family Istanbul scenario.
    """
    hotels = search_hotels_for_group("G-0001")

    assert len(hotels) > 0
    assert hotels[0]["hotel_id"] == "HT-045"
    assert hotels[0]["total_price_rub"] == 56300


def test_search_hotels_for_group_g0002() -> None:
    """
    Checks ranked hotel search for Dubai beach scenario.
    """
    hotels = search_hotels_for_group("G-0002")

    assert len(hotels) > 0
    assert hotels[0]["hotel_id"] == "HT-101"