from typing import Any


def calculate_independent_trip_total(
    flight: dict[str, Any] | None,
    hotel: dict[str, Any] | None,
) -> int | None:
    """
    Calculates total price for independent trip booking.

    Independent booking means that the agent combines a selected flight and
    a selected hotel. The hotel dictionary is expected to contain either
    total_price_rub or price_per_night_rub with nights.

    @param flight Selected flight dictionary.
    @param hotel Selected hotel dictionary.
    @return Total trip price in rubles or None if calculation is impossible.
    """
    if flight is None or hotel is None:
        return None

    if "price_rub" not in flight:
        return None

    flight_price = int(flight["price_rub"])

    if "total_price_rub" in hotel:
        hotel_total_price = int(hotel["total_price_rub"])
    elif "price_per_night_rub" in hotel and "nights" in hotel:
        hotel_total_price = int(hotel["price_per_night_rub"]) * int(hotel["nights"])
    else:
        return None

    return flight_price + hotel_total_price


def calculate_package_trip_total(
    tour: dict[str, Any] | None,
) -> int | None:
    """
    Calculates total price for package tour booking.

    @param tour Selected package tour dictionary.
    @return Package tour price in rubles or None if tour is missing.
    """
    if tour is None:
        return None

    if "total_price_rub" not in tour:
        return None

    return int(tour["total_price_rub"])


def calculate_budget_gap(
    total_price_rub: int | None,
    budget_rub: int | None,
) -> int | None:
    """
    Calculates difference between total price and budget.

    Positive value means budget overrun.
    Negative value means remaining budget.

    @param total_price_rub Total trip price in rubles.
    @param budget_rub Available budget in rubles.
    @return Budget gap in rubles or None if calculation is impossible.
    """
    if total_price_rub is None or budget_rub is None:
        return None

    return int(total_price_rub) - int(budget_rub)


def check_budget(
    total_price_rub: int | None,
    budget_rub: int | None,
) -> bool | None:
    """
    Checks whether total price fits the available budget.

    @param total_price_rub Total trip price in rubles.
    @param budget_rub Available budget in rubles.
    @return True if price is within budget, False if over budget, None if unknown.
    """
    budget_gap = calculate_budget_gap(total_price_rub, budget_rub)

    if budget_gap is None:
        return None

    return budget_gap <= 0


def build_budget_summary(
    total_price_rub: int | None,
    budget_rub: int | None,
) -> dict[str, Any]:
    """
    Builds structured budget summary for agent output.

    @param total_price_rub Total trip price in rubles.
    @param budget_rub Available budget in rubles.
    @return Dictionary with total price, budget, budget status and budget gap.
    """
    budget_gap = calculate_budget_gap(total_price_rub, budget_rub)

    return {
        "total_price_rub": total_price_rub,
        "budget_rub": budget_rub,
        "budget_ok": check_budget(total_price_rub, budget_rub),
        "budget_gap_rub": budget_gap,
    }


def build_independent_budget_summary(
    flight: dict[str, Any] | None,
    hotel: dict[str, Any] | None,
    budget_rub: int | None,
) -> dict[str, Any]:
    """
    Builds budget summary for independent flight plus hotel option.

    @param flight Selected flight dictionary.
    @param hotel Selected hotel dictionary.
    @param budget_rub Available group budget in rubles.
    @return Structured independent option budget summary.
    """
    total_price = calculate_independent_trip_total(flight, hotel)
    summary = build_budget_summary(total_price, budget_rub)

    summary.update(
        {
            "option_type": "independent",
            "flight_id": flight.get("flight_id") if flight else None,
            "hotel_id": hotel.get("hotel_id") if hotel else None,
        }
    )

    return summary


def build_package_budget_summary(
    tour: dict[str, Any] | None,
    budget_rub: int | None,
) -> dict[str, Any]:
    """
    Builds budget summary for package tour option.

    @param tour Selected package tour dictionary.
    @param budget_rub Available group budget in rubles.
    @return Structured package option budget summary.
    """
    total_price = calculate_package_trip_total(tour)
    summary = build_budget_summary(total_price, budget_rub)

    summary.update(
        {
            "option_type": "package",
            "tour_id": tour.get("tour_id") if tour else None,
            "hotel_id": tour.get("hotel_id") if tour else None,
        }
    )

    return summary