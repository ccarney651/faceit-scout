"""Control-map sub-map lookup (owscout.maps)."""

from owscout.maps import CONTROL_SUBMAPS, is_control_map, submaps_for


def test_control_map_returns_submaps_case_insensitive() -> None:
    assert submaps_for("Ilios") == ["Lighthouse", "Ruins", "Well"]
    assert submaps_for("ILIOS") == ["Lighthouse", "Ruins", "Well"]
    assert is_control_map("Oasis")


def test_alias_maps_resolve() -> None:
    assert submaps_for("Antarctica") == ["Icebreaker", "Labs", "Sublevel"]
    assert submaps_for("Lijiang") == submaps_for("Lijiang Tower")


def test_non_control_maps_have_no_submaps() -> None:
    assert submaps_for("King's Row") == []
    assert submaps_for("Dorado") == []
    assert not is_control_map("New Junk City")  # Flashpoint, not control
    assert submaps_for(None) == []
    assert submaps_for("") == []


def test_returned_list_is_a_copy() -> None:
    # Callers must not be able to mutate the shared reference data.
    got = submaps_for("Ilios")
    got.append("Tampered")
    assert CONTROL_SUBMAPS["ilios"] == ["Lighthouse", "Ruins", "Well"]
