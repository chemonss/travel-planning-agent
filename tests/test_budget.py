from travel_agent.tools.budget import (
    build_budget_summary,
    build_independent_budget_summary,
    build_package_budget_summary,
    calculate_budget_gap,
    calculate_independent_trip_total,
    calculate_package_trip_total,
    check_budget,
)


def test_calculate_independent_trip_total_with_total_hotel_price() -> None:
    """
    Checks independent trip total calculation with hotel total price.
    """
    flight = {
        "flight_id": "FL-102",
        "price_rub": 74200,
    }

    hotel = {
        "hotel_id": "HT-045",
        "total_price_rub": 56300,
    }

    assert calculate_independent_trip_total(flight, hotel) == 130500


def test_calculate_independent_trip_total_with_nights() -> None:
    """
    Checks independent trip total calculation from hotel nightly price.
    """
    flight = {
        "flight_id": "FL-102",
        "price_rub": 74200,
    }

    hotel = {
        "hotel_id": "HT-045",
        "price_per_night_rub": 11260,
        "nights": 5,
    }

    assert calculate_independent_trip_total(flight, hotel) == 130500


def test_calculate_package_trip_total() -> None:
    """
    Checks package tour total calculation.
    """
    tour = {
        "tour_id": "TR-020",
        "total_price_rub": 214700,
    }

    assert calculate_package_trip_total(tour) == 214700


def test_calculate_budget_gap() -> None:
    """
    Checks budget gap calculation.
    """
    assert calculate_budget_gap(130500, 180000) == -49500
    assert calculate_budget_gap(230000, 180000) == 50000


def test_check_budget() -> None:
    """
    Checks budget status calculation.
    """
    assert check_budget(130500, 180000) is True
    assert check_budget(230000, 180000) is False
    assert check_budget(None, 180000) is None


def test_build_budget_summary() -> None:
    """
    Checks structured budget summary.
    """
    summary = build_budget_summary(
        total_price_rub=130500,
        budget_rub=180000,
    )

    assert summary == {
        "total_price_rub": 130500,
        "budget_rub": 180000,
        "budget_ok": True,
        "budget_gap_rub": -49500,
    }


def test_build_independent_budget_summary() -> None:
    """
    Checks independent option budget summary.
    """
    flight = {
        "flight_id": "FL-102",
        "price_rub": 74200,
    }

    hotel = {
        "hotel_id": "HT-045",
        "total_price_rub": 56300,
    }

    summary = build_independent_budget_summary(
        flight=flight,
        hotel=hotel,
        budget_rub=180000,
    )

    assert summary["option_type"] == "independent"
    assert summary["flight_id"] == "FL-102"
    assert summary["hotel_id"] == "HT-045"
    assert summary["total_price_rub"] == 130500
    assert summary["budget_ok"] is True
    assert summary["budget_gap_rub"] == -49500


def test_build_package_budget_summary() -> None:
    """
    Checks package option budget summary.
    """
    tour = {
        "tour_id": "TR-020",
        "hotel_id": "HT-101",
        "total_price_rub": 214700,
    }

    summary = build_package_budget_summary(
        tour=tour,
        budget_rub=220000,
    )

    assert summary["option_type"] == "package"
    assert summary["tour_id"] == "TR-020"
    assert summary["hotel_id"] == "HT-101"
    assert summary["total_price_rub"] == 214700
    assert summary["budget_ok"] is True
    assert summary["budget_gap_rub"] == -5300