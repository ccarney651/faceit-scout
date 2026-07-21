"""Capture keybinds: resolution from stored settings, and conflict detection."""

from owscout.capture import (
    DEFAULT_KEYBINDS,
    SETTING_PREFIX,
    keybind_conflicts,
    resolve_keybinds,
)


def test_defaults_apply_when_nothing_is_stored() -> None:
    assert resolve_keybinds({}) == DEFAULT_KEYBINDS


def test_stored_binds_override_only_what_they_set() -> None:
    binds = resolve_keybinds({f"{SETTING_PREFIX}snapshot": "F10"})
    assert binds["snapshot"] == "f10"          # normalised to lower case
    assert binds["round"] == DEFAULT_KEYBINDS["round"]


def test_junk_settings_cannot_leave_an_action_unbound() -> None:
    """A blank or unknown row must fall back, never yield an empty hotkey - an
    empty string would raise inside keyboard.add_hotkey mid-capture."""
    binds = resolve_keybinds({f"{SETTING_PREFIX}snapshot": "  ",
                              f"{SETTING_PREFIX}nonsense": "f4"})
    assert binds == DEFAULT_KEYBINDS
    assert "nonsense" not in binds


def test_duplicate_key_is_reported() -> None:
    """One press firing two actions is silent corruption: a snapshot AND a round
    advance from a single keypress."""
    binds = {**DEFAULT_KEYBINDS, "undo": DEFAULT_KEYBINDS["snapshot"]}
    problems = keybind_conflicts(binds)
    assert problems and "F8" in problems[0]


def test_esc_is_rejected() -> None:
    assert keybind_conflicts({**DEFAULT_KEYBINDS, "round": "esc"})


def test_default_keybinds_are_themselves_valid() -> None:
    assert keybind_conflicts(DEFAULT_KEYBINDS) == []


def test_done_is_a_configurable_bind_and_never_esc() -> None:
    """Stopping capture must NOT be on Esc (Esc opens the OW menu). It's a normal
    rebindable action with a non-Esc default, and Esc stays rejected for it."""
    assert "done" in DEFAULT_KEYBINDS
    assert DEFAULT_KEYBINDS["done"] not in ("esc", "escape")
    assert keybind_conflicts({**DEFAULT_KEYBINDS, "done": "esc"})   # rejected
    # a sane rebind is accepted
    assert keybind_conflicts({**DEFAULT_KEYBINDS, "done": "f12"}) == []
