"""The four pages must stay one interface, not four that resemble each other.

`docs/theme.css` is the shared design system: tokens plus the handful of
primitives every page reads. It only works if the pages actually go through
it. Every finding these tests guard against was a page reaching around the
token layer and hardcoding what the token already said, and none of them
were visible from any single file:

  - `color:#fff` on `background:var(--accent)` looks correct in the light
    palette it was written in and fails WCAG AA in all seven dark ones
    (teal bottomed out at 1.93:1). `--on-accent` exists precisely so the
    pairing travels with the accent; eight sites had bypassed it.
  - `.ticon{display:block}` stacked the icon above the label in all sixteen
    icon buttons on the capture pages, and the `vertical-align:-2px` every
    one of them carried was a no-op that made the intent unmistakable.
  - `docs/scrims.html` was the only themed page with no palette bootstrap,
    so a palette chosen anywhere else silently did not apply there.
  - `var(--bad,#e56a6a)` fallbacks named colours the tokens had long since
    moved off, so the fallback and the token disagreed about the same idea.

The shape they share: a page states a value the design system already owns.
Nothing breaks, nothing warns, and the drift is only visible by reading two
files side by side — which is what these tests do.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DASHBOARD = ROOT / "faceit_sync" / "dashboard"

# CI regenerates docs/index.html from faceit_sync/dashboard/head.html on every
# run, so a finding there would be reported against a file nobody edits. The
# dashboard is covered at its source instead — head.html is in PAGES below.
# Frozen season archives (docs/s9/index.html, ...) are the same file one step
# further along: generated from the same template and then deliberately never
# rebuilt, so a finding against one could not be acted on even in principle.
GENERATED = {"index.html"} | {f"s{n}/index.html" for n in range(1, 30)}

PAGES = sorted(
    [p for p in DOCS.rglob("*.html") if p.relative_to(DOCS).as_posix() not in GENERATED]
    + [DASHBOARD / "head.html"]
)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def stylesheet(html: str) -> str:
    """Every <style> block on a page, comments stripped."""
    blocks = re.findall(r"<style>(.*?)</style>", html, re.S)
    return re.sub(r"/\*.*?\*/", "", "\n".join(blocks), flags=re.S)


def declaration_blocks(css: str) -> list[tuple[str, str]]:
    """(selector, declarations) for every rule, including inside @media."""
    return [
        (" ".join(sel.split()), " ".join(decl.split()))
        for sel, decl in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)
        if sel.strip() and not sel.strip().startswith("@")
    ]


def inline_styles(html: str) -> list[str]:
    return [" ".join(m.split()) for m in re.findall(r'style="([^"]*)"', html)]


LITERAL_COLOR = re.compile(r"(?<![-\w])(#[0-9a-fA-F]{3,8}|white|black)\b")


@pytest.mark.parametrize("page", PAGES, ids=rel)
def test_accent_backgrounds_use_the_on_accent_token(page: Path) -> None:
    """A literal text colour on an accent background is a contrast bug waiting
    for a palette switch. `--accent` and `--on-accent` are defined as a pair in
    every palette and every mode; anything painting text on the accent must
    read the paired token rather than restating one palette's answer."""
    html = page.read_text(encoding="utf-8")
    offenders = []
    for where, decl in [(sel, d) for sel, d in declaration_blocks(stylesheet(html))] + [
        ("inline style=", s) for s in inline_styles(html)
    ]:
        if "var(--accent)" not in decl:
            continue
        if not re.search(r"background(-color)?\s*:[^;]*var\(--accent\)", decl):
            continue
        colour = re.search(r"(?<!-)\bcolor\s*:\s*([^;]+)", decl)
        if colour and LITERAL_COLOR.search(colour.group(1)):
            offenders.append(f"{where} {{ {decl} }}")
    assert not offenders, (
        f"{rel(page)} paints literal text on an accent background; use "
        f"var(--on-accent):\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("page", PAGES, ids=rel)
def test_every_themed_page_applies_the_stored_palette(page: Path) -> None:
    """The palette lives in one localStorage key shared across the origin, so
    picking one on any page must apply on all of them. A page that links the
    shared stylesheet but never reads the key is stuck on the default and
    looks like a different product the moment someone changes palette."""
    html = page.read_text(encoding="utf-8")
    # head.html does not link the stylesheet, it carries the __THEME_CSS__
    # placeholder the exporter substitutes; matching only "theme.css" silently
    # skipped the dashboard, which is the page the key belongs to.
    if "theme.css" not in html and "__THEME_CSS__" not in html:
        pytest.skip("page does not use the shared stylesheet")
    assert "owdb.palette" in html, (
        f"{rel(page)} links theme.css but never reads the owdb.palette key, so "
        "a palette chosen on another page will not apply here"
    )
    assert "data-palette" in html, (
        f"{rel(page)} reads the palette but never sets data-palette on <html>"
    )


@pytest.mark.parametrize("page", PAGES, ids=rel)
def test_button_icons_lay_out_inline(page: Path) -> None:
    """`.ticon` is only ever used inside a button beside a text label, and
    every use site sets `vertical-align` — which does nothing to a block box.
    `display:block` made each of those buttons two lines tall and broke the
    alignment of every row they sat in."""
    css = stylesheet(page.read_text(encoding="utf-8"))
    for sel, decl in declaration_blocks(css):
        if sel != ".ticon":
            continue
        assert "display:block" not in decl, (
            f"{rel(page)} sets .ticon{{display:block}}, which stacks the icon "
            "above its button label and makes the vertical-align on every use "
            "site a no-op"
        )


def keyframe_free(css: str) -> str:
    """Drop @keyframes bodies — `from`/`to` blocks collide across files for
    reasons that say nothing about shared components."""
    return re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css, flags=re.S)


def rule_index(page: Path) -> dict[str, str]:
    """selector -> declarations for one page, keyframes excluded."""
    css = keyframe_free(stylesheet(page.read_text(encoding="utf-8")))
    return dict(declaration_blocks(css))


def test_the_two_capture_pages_style_shared_selectors_identically() -> None:
    """docs/capture/index.html and docs/capture/scrim.html are the same tool
    pointed at league play and at scrims. Their JS is a known fork that
    tools/capture_divergence.py tracks, but their CSS was never meant to be
    one: the same `button` was 6px/7px-11px on one page and 7px/9px-13px on
    the other, so every control silently changed size when an operator moved
    between them. Worse, the modal on scrim.html grew a max-height and a
    scrolling body and index.html never got it — a fix that landed on one
    twin only. A selector defined on both must mean the same thing on both."""
    left = rule_index(DOCS / "capture" / "index.html")
    right = rule_index(DOCS / "capture" / "scrim.html")
    diverged = [
        f"{sel}\n      index: {left[sel]}\n      scrim: {right[sel]}"
        for sel in sorted(left.keys() & right.keys())
        if left[sel] != right[sel]
    ]
    assert not diverged, (
        "capture/index.html and capture/scrim.html style shared selectors "
        "differently:\n    " + "\n    ".join(diverged)
    )


def test_the_two_data_pages_do_not_define_the_same_selector() -> None:
    """The dashboard and scrims.html may not both style the same selector, and
    the two ways they can break that have opposite fixes.

    Identical means shared — `.card`, `.section-h`, the whole table and chip
    layer were written out byte-for-byte in both — and duplication is how they
    drifted: `.poolgrid` ended up auto-fit/210px on one and auto-fill/240px on
    the other. Those belong in docs/theme.css.

    Different means the name is doing two jobs. `.wl` was a row of filled W/L
    pips on the dashboard and a coloured W-L-D count on scrims, so the same
    record rendered as two different components depending on the page. Those
    need two names, not one stylesheet entry."""
    dash = rule_index(DASHBOARD / "head.html")
    scrims = rule_index(DOCS / "scrims.html")
    both = sorted(dash.keys() & scrims.keys())
    duplicated = [s for s in both if dash[s] == scrims[s]]
    collided = [s for s in both if dash[s] != scrims[s]]
    assert not duplicated, (
        "identical in faceit_sync/dashboard/head.html and docs/scrims.html, so "
        "these belong in docs/theme.css:\n    " + "\n    ".join(duplicated)
    )
    assert not collided, (
        "these selectors mean different things on the dashboard and on "
        "scrims.html; give the two components two names:\n    "
        + "\n    ".join(collided)
    )


def theme_tokens() -> dict[str, str]:
    """Token -> value from the default :root block of the shared stylesheet."""
    css = (DOCS / "theme.css").read_text(encoding="utf-8")
    root = re.search(r":root\{(.*?)\}", css, re.S)
    assert root, "theme.css has no bare :root block"
    return {
        name: value.strip()
        for name, value in re.findall(r"(--[-\w]+)\s*:\s*([^;]+)", root.group(1))
    }


@pytest.mark.parametrize("page", PAGES, ids=rel)
def test_custom_property_fallbacks_match_the_token(page: Path) -> None:
    """`var(--good,#4ac28a)` is a promise that the fallback is what the token
    says. These were copied from a palette two redesigns ago, so the fallback
    and the token had drifted to different colours for the same idea. The
    stylesheet always loads, so a fallback that disagrees is dead weight that
    reads as a second, competing source of truth."""
    tokens = theme_tokens()
    html = page.read_text(encoding="utf-8")
    stale = []
    for name, fallback in re.findall(r"var\(\s*(--[-\w]+)\s*,\s*([^)]+)\)", html):
        fallback = fallback.strip()
        expected = tokens.get(name)
        if expected is not None and fallback.lower() != expected.lower():
            stale.append(f"var({name},{fallback}) — theme.css says {expected}")
    assert not stale, (
        f"{rel(page)} has custom-property fallbacks that disagree with the "
        f"token; drop the fallback or match it:\n  " + "\n  ".join(stale)
    )


def test_frozen_season_archives_are_excluded_from_page_checks() -> None:
    """A frozen archive is a generated export that is then deliberately never
    rebuilt, so a finding against one could not be acted on even in principle -
    docs/index.html's reasoning, one step further along."""
    assert "s9/index.html" in GENERATED
