from travel_agent.tools.groups import get_full_group_profile


def test_get_full_group_profile_g0001() -> None:
    """
    Checks that the full group profile is correctly loaded.
    """
    profile = get_full_group_profile("G-0001")

    assert profile["group"]["group_id"] == "G-0001"
    assert profile["summary"]["destination"] == "IST"
    assert profile["summary"]["nights"] == 5
    assert profile["summary"]["traveler_count"] == 3
    assert profile["summary"]["has_children"] is True
    assert len(profile["members"]) == 3
    assert len(profile["preferences"]) > 0