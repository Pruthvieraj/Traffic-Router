"""Automated layout/regression tests for templates/click_router.html,
using a real browser engine (Playwright + Chromium) against a real running
copy of the app.

WHY THIS FILE EXISTS: every other test in tests/ verifies LOGIC (correct
routes, correct costs, correct API responses) — none of them verify that
the page actually RENDERS correctly. That gap is not hypothetical: a real
bug shipped through a full green test suite and multiple rounds of manual
screenshots before a user caught it live — the topbar had a fixed height
combined with flex-wrap, so on a narrower browser window the second row of
controls (Solve route, Clear points) overflowed past the bar and rendered
on top of the map instead of inside it. Nothing here would have failed
before that fix; these tests exist so the same class of bug can't ship
silently again.

Skipped automatically (not failed) if the `playwright` package or its
Chromium browser isn't installed — this keeps `pytest tests/` runnable
with just `pip install -r requirements.txt && pip install pytest` for
everyone who doesn't need the visual checks, while CI (which does install
Playwright — see .github/workflows/tests.yml) always runs them for real.

Setup (only needed to run THIS file — not required for the rest of the
suite):
    pip install playwright
    playwright install --with-deps chromium
    pytest tests/test_layout.py -v
"""

import contextlib
import os
import socket
import subprocess
import time
import urllib.request

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed — see this file's docstring to enable layout tests",
)
from playwright.sync_api import sync_playwright  # noqa: E402

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _chromium_available():
    """True iff Playwright can actually launch a Chromium browser — the
    Python package can be installed without its browser binaries (that's a
    separate `playwright install` step), so check for real rather than
    assuming."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        return True
    except Exception:
        return False


if not _chromium_available():
    pytest.skip(
        "Playwright's Chromium browser isn't installed — run `playwright install --with-deps chromium` "
        "to enable tests/test_layout.py",
        allow_module_level=True,
    )


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    """Runs the REAL app.py (not the Flask test client) as a subprocess, on
    its own free port, so these tests exercise exactly what a browser
    hitting the deployed app would see — full CSS layout, real Leaflet
    initialization, everything. Torn down at the end of the module."""
    port = _free_port()
    env = os.environ.copy()
    env["PORT"] = str(port)
    proc = subprocess.Popen(
        ["python3", "app.py"], cwd=_PROJECT_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base_url, timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.terminate()
        raise RuntimeError("app.py didn't start in time for layout tests")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _no_topbar_overflow(page):
    """Every visible direct control in #topbar must render fully within
    #topbar's own box — this is the exact property that broke: a wrapped
    second row spilling out past a fixed-height container."""
    return page.evaluate("""
        () => {
            const bar = document.getElementById('topbar').getBoundingClientRect();
            const kids = Array.from(document.querySelectorAll(
                '#topbar select, #topbar button, #topbar #searchWrap, #topbar .method-wrap, #topbar #brand'
            ));
            return kids
                .filter(el => el.offsetParent !== null) // only visible elements
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.bottom > bar.bottom + 1 || r.top < bar.top - 1;
                })
                .map(el => el.id || el.className || el.tagName);
        }
    """)


@pytest.mark.parametrize("width", [375, 1000, 1280, 1440, 1920])
def test_topbar_controls_never_overflow_the_bar(live_server, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    overflowing = _no_topbar_overflow(page)
    page.close()
    assert overflowing == [], f"topbar controls render outside #topbar at width={width}px: {overflowing}"


def test_content_area_starts_exactly_where_topbar_ends(live_server, browser):
    """The map/panel container must have zero gap from (and zero overlap
    with) the topbar, regardless of how many rows the topbar wrapped to —
    this is what makes the layout robust to any window width, rather than
    relying on a hardcoded pixel offset that only happened to be correct
    for one specific topbar height."""
    page = browser.new_page(viewport={"width": 1000, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    gap = page.evaluate("""
        () => {
            const bar = document.getElementById('topbar').getBoundingClientRect();
            const content = document.getElementById('content').getBoundingClientRect();
            return Math.abs(content.top - bar.bottom);
        }
    """)
    page.close()
    assert gap < 1


def test_fleet_mode_relabels_first_pin_as_depot(live_server, browser):
    """Regression check for the multi-vehicle UI: switching to >1 vehicle
    must relabel the first pin 'D' (Depot) instead of 'S' (Start) — this is
    how a user tells fleet mode is actually active, not just cosmetic."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.select_option("#vehicleSelect", "3")
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    label = page.evaluate("document.querySelector('.pin-label').textContent")
    page.close()
    assert label == "D"


def test_single_vehicle_mode_still_labels_first_pin_as_start(live_server, browser):
    """The flip side of the above — default (1 vehicle) mode must be
    completely unaffected by the fleet-mode relabeling logic."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    label = page.evaluate("document.querySelector('.pin-label').textContent")
    page.close()
    assert label == "S"


def test_capacity_input_only_shows_in_fleet_mode(live_server, browser):
    """The 'Max stops/vehicle' input should be hidden in single-vehicle
    mode (the default) and appear only once multi-vehicle mode is
    selected — it's meaningless outside fleet mode and shouldn't clutter
    the topbar there."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    hidden_initially = page.evaluate("document.getElementById('capacityWrap').offsetParent === null")
    page.select_option("#vehicleSelect", "2")
    visible_after = page.evaluate("document.getElementById('capacityWrap').offsetParent !== null")
    page.select_option("#vehicleSelect", "1")
    hidden_again = page.evaluate("document.getElementById('capacityWrap').offsetParent === null")

    page.close()
    assert hidden_initially, "capacity input should be hidden by default (1 vehicle)"
    assert visible_after, "capacity input should appear once multi-vehicle mode is selected"
    assert hidden_again, "capacity input should hide again when switching back to 1 vehicle"


def test_city_dropdown_covers_pan_india(live_server, browser):
    """Regression check for the pan-India expansion: the city dropdown
    used to only offer 5 NCR-adjacent cities (Bengaluru, Mumbai, Pune,
    Gurgaon, Noida) — it should now offer at least 17, spanning the rest
    of the country too."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    values = page.eval_on_selector_all("#citySelect option", "els => els.map(e => e.value)")
    page.close()
    assert len(values) >= 17
    assert "Bengaluru" in values and "Delhi" in values and "Chennai" in values


def test_voice_search_mic_button_has_no_stray_dropdown_chevron(live_server, browser):
    """Regression check: the mic button is a plain <button> inside
    #topbar, and a generic '#topbar select, #topbar button' rule gives
    every such button a dropdown-chevron background image unless
    specifically overridden — this locks in that override (a real bug
    caught once during development: the mic button rendered with a
    stray chevron baked into it)."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    style = page.evaluate("""
        () => {
            const cs = getComputedStyle(document.getElementById('micBtn'));
            return { bgImage: cs.backgroundImage, width: parseFloat(cs.width) };
        }
    """)
    page.close()
    assert style["bgImage"] == "none"
    assert style["width"] <= 24  # a real icon-button size, not a stretched generic control


def test_incident_button_renders_for_every_stop_marker_line(live_server, browser):
    """Exercises renderDirections() directly with synthetic OSRM-shaped
    data (no real network needed) and checks the 'Simulate incident here'
    button appears exactly once per stop-arrival line — the UI hook the
    dynamic-re-optimization feature depends on."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    button_count = page.evaluate("""
        () => {
            const legs = [
                { steps: [
                    { maneuver: { type: 'depart' }, name: 'A Road', distance: 200 },
                    { maneuver: { type: 'arrive' }, name: '', distance: 0 },
                ]},
                { steps: [
                    { maneuver: { type: 'depart' }, name: 'B Road', distance: 100 },
                    { maneuver: { type: 'arrive' }, name: '', distance: 0 },
                ]},
            ];
            renderDirections(legs, [[0,0],[1,1],[2,2]]);
            return document.querySelectorAll('.incident-btn').length;
        }
    """)
    page.close()
    assert button_count == 2  # one stop-marker line per leg
