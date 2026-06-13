from travel_agent.tools.trip_options import (
    get_best_candidate,
    get_trip_options_for_group,
    select_recommended_option,
)


def test_get_best_candidate() -> None:
    """
    Checks best candidate extraction.
    """
    assert get_best_candidate([]) is None
    assert get_best_candidate([{"id": "A"}, {"id": "B"}]) == {"id": "A"}


def test_get_trip_options_for_group_g0001() -> None:
    """
    Checks complete trip option assembly for Istanbul family scenario.
    """
    result = get_trip_options_for_group("G-0001")

    assert result["group_profile"]["summary"]["group_id"] == "G-0001"

    assert result["best"]["flight"] is not None
    assert result["best"]["flight"]["flight_id"] == "FL-102"

    assert result["best"]["hotel"] is not None
    assert result["best"]["hotel"]["hotel_id"] == "HT-045"

    independent_budget = result["options"]["independent"]["budget"]

    assert independent_budget["total_price_rub"] == 130500
    assert independent_budget["budget_rub"] == 180000
    assert independent_budget["budget_ok"] is True
    assert independent_budget["budget_gap_rub"] == -49500

    assert result["recommended_option"] is not None
    assert result["recommended_option"]["option_type"] == "independent"


def test_get_trip_options_for_group_g0002() -> None:
    """
    Checks complete trip option assembly for Dubai package-tour scenario.
    """
    result = get_trip_options_for_group("G-0002")

    assert result["group_profile"]["summary"]["group_id"] == "G-0002"

    assert result["best"]["flight"] is not None
    assert result["best"]["flight"]["flight_id"] == "FL-205"

    assert result["best"]["hotel"] is not None
    assert result["best"]["hotel"]["hotel_id"] == "HT-101"

    assert result["best"]["tour"] is not None
    assert result["best"]["tour"]["tour_id"] == "TR-020"

    package_budget = result["options"]["package"]["budget"]

    assert package_budget["total_price_rub"] == 214700
    assert package_budget["budget_rub"] == 220000
    assert package_budget["budget_ok"] is True

    assert result["recommended_option"] is not None
    assert result["recommended_option"]["option_type"] == "package"


def test_select_recommended_option_prefers_reasonable_package() -> None:
    """
    Checks that a reasonable package option is preferred.
    """
    independent_option = {
        "available": True,
        "option_type": "independent",
        "budget": {
            "budget_ok": True,
        },
    }

    package_option = {
        "available": True,
        "option_type": "package",
        "budget": {
            "budget_ok": True,
        },
        "comparison_with_independent": {
            "tour_is_reasonable": True,
        },
    }

    recommended = select_recommended_option(
        independent_option=independent_option,
        package_option=package_option,
    )

    assert recommended is package_option


def test_select_recommended_option_falls_back_to_independent() -> None:
    """
    Checks fallback to independent option when package is too expensive.
    """
    independent_option = {
        "available": True,
        "option_type": "independent",
        "budget": {
            "budget_ok": True,
        },
    }

    package_option = {
        "available": True,
        "option_type": "package",
        "budget": {
            "budget_ok": True,
        },
        "comparison_with_independent": {
            "tour_is_reasonable": False,
        },
    }

    recommended = select_recommended_option(
        independent_option=independent_option,
        package_option=package_option,
    )

    assert recommended is independent_option