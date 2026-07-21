"""CaptureControls: the handle the overlay buttons use to drive a live capture.

The contract that matters: a click can only ever fire a bound handler while the
capture is running - never before it starts, never after it ends - so an
overlay button can't poke a half-set-up or finished capture.
"""

from __future__ import annotations

from owscout.capture import CaptureControls


def _bind(c: CaptureControls, calls: list[str], *, submaps=(), phased=False):
    c._bind(
        snapshot=lambda: calls.append("snap"),
        next_round=lambda: calls.append("round"),
        toggle_attack=lambda: calls.append("attack"),
        undo=lambda: calls.append("undo"),
        done=lambda: calls.append("done"),
        pick_sub=lambda name: calls.append(f"sub:{name}"),
        submaps=submaps, phased=phased, map_category="control" if submaps else "push",
    )


def test_actions_are_noops_before_bind() -> None:
    c = CaptureControls()
    for fn in (c.snapshot, c.next_round, c.toggle_attack, c.undo, c.done):
        fn()               # must not raise
    c.pick_sub("Gardens")  # must not raise
    # nothing was wired, so nothing happened - and the map facts are still empty
    assert c.submaps == () and c.phased is False


def test_actions_fire_bound_handlers_after_bind() -> None:
    c = CaptureControls()
    calls: list[str] = []
    _bind(c, calls, submaps=("City Center", "Gardens"))
    c.snapshot(); c.next_round(); c.undo(); c.done(); c.pick_sub("Gardens")
    assert calls == ["snap", "round", "undo", "done", "sub:Gardens"]


def test_map_facts_exposed_for_the_overlay() -> None:
    c = CaptureControls()
    _bind(c, [], submaps=("A", "B", "C"))
    assert c.submaps == ("A", "B", "C")
    assert c.phased is False
    assert c.map_category == "control"

    c2 = CaptureControls()
    _bind(c2, [], phased=True)
    assert c2.submaps == () and c2.phased is True


def test_end_makes_further_clicks_noops() -> None:
    c = CaptureControls()
    calls: list[str] = []
    _bind(c, calls)
    c.snapshot()
    c._end()
    c.snapshot(); c.next_round(); c.pick_sub("X")   # all ignored now
    assert calls == ["snap"]


def test_on_ready_is_called_on_bind_and_survives_a_throw() -> None:
    fired: list[int] = []
    c = CaptureControls()
    c.on_ready = lambda: fired.append(1)
    _bind(c, [])
    assert fired == [1]

    # A display that throws in on_ready must not break binding (capture goes on).
    c2 = CaptureControls()
    def boom() -> None:
        raise RuntimeError("overlay gone")
    c2.on_ready = boom
    _bind(c2, [])          # must not raise
    assert c2._active is True
