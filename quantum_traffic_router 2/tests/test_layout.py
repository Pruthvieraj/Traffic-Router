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
import json
import os
import socket
import subprocess
import time
import urllib.parse
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


# ---------- search fallback for addresses not in OpenStreetMap's database ----------
# (a real user report: small housing societies like "Sukhwani Gracia C" in
# Pune are frequently unmapped at the specific wing/tower level, even when
# the base society name IS in OpenStreetMap — see fetchSuggestions()'s
# progressively-broader-query fallback in the template.)

def test_search_falls_back_to_a_broader_query_and_finds_a_result(live_server, browser):
    """Simulates exactly the reported real-world failure: the exact query
    (with a trailing wing letter) returns nothing from the search service,
    but the base building name without that suffix does exist — the
    fallback should still surface it, rather than reporting no match."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    def handle_route(route):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query).get("q", [""])[0]
        if q == "Sukhwani Gracia, Pune, India":  # the stripped-suffix fallback variant
            route.fulfill(json=[{
                "display_name": "Sukhwani Gracia, Wakad, Pune, Maharashtra, India",
                "lat": "18.5980", "lon": "73.7629",
            }])
        else:  # the exact query (still has "C") and every other variant: nothing found
            route.fulfill(json=[])

    page.route("**nominatim.openstreetmap.org/search**", handle_route)
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.select_option("#citySelect", "Pune")
    page.fill("#searchInput", "Sukhwani Gracia C")
    page.wait_for_function(
        "document.getElementById('suggestions').style.display === 'block'", timeout=5000,
    )
    text = page.inner_text("#suggestions")
    page.close()
    assert "Sukhwani Gracia" in text


def test_search_shows_a_helpful_hint_when_nothing_is_found_anywhere(live_server, browser):
    """When even the broadest fallback query comes back empty (a place
    genuinely not in OpenStreetMap's free database — common for newer
    housing societies), the search box should say so and point at the
    guaranteed fallback (click the spot on the map) rather than just going
    quiet, which looks like the search is broken rather than the data
    being incomplete."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.route("**nominatim.openstreetmap.org/search**", lambda route: route.fulfill(json=[]))
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.fill("#searchInput", "Totally Nonexistent Society Zzzqx")
    page.wait_for_function(
        "document.getElementById('suggestions').style.display === 'block'", timeout=5000,
    )
    text = page.inner_text("#suggestions").lower()
    page.close()
    assert "click" in text and ("map" in text or "satellite" in text)


# ---------- custom info-icon tooltip (replaces native title=) ----------

def test_info_icon_tooltip_shows_its_text_on_click_and_hides_on_outside_click(live_server, browser):
    """Regression check for the tooltip redesign: clicking an info icon
    should show the shared #iconTooltip bubble with that icon's original
    title text (moved to data-tip so the native browser tooltip doesn't
    also fire), and clicking elsewhere should hide it again."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    icon = page.locator(".info-icon").first
    assert icon.get_attribute("title") is None  # native tooltip attribute removed
    expected = icon.get_attribute("data-tip")
    assert expected and len(expected) > 10

    icon.click()
    page.wait_for_function(
        "document.getElementById('iconTooltip').classList.contains('visible')", timeout=3000,
    )
    shown_text = page.inner_text("#iconTooltip")
    assert shown_text == expected

    page.mouse.click(700, 700)  # click somewhere unrelated on the map
    page.wait_for_function(
        "!document.getElementById('iconTooltip').classList.contains('visible')", timeout=3000,
    )
    page.close()


def test_info_icon_tooltip_stays_within_the_viewport(live_server, browser):
    """The vehicle-select info icon sits near the middle of a busy topbar —
    the tooltip bubble must never be positioned so it clips off the left
    or right edge of the window, regardless of window width."""
    page = browser.new_page(viewport={"width": 375, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.locator(".info-icon").first.click()
    page.wait_for_function(
        "document.getElementById('iconTooltip').classList.contains('visible')", timeout=3000,
    )
    box = page.evaluate("""
        () => {
            const r = document.getElementById('iconTooltip').getBoundingClientRect();
            return {left: r.left, right: r.right};
        }
    """)
    page.close()
    assert box["left"] >= 0
    assert box["right"] <= 375


# ---------- bulk import (paste text / upload a .csv or .txt) ----------

def test_bulk_import_adds_direct_coordinates_and_geocoded_addresses(live_server, browser):
    """A pasted block mixing a direct "lat, lon" line (added with no
    network call at all) and a plain address line (geocoded through the
    same Nominatim endpoint the search box uses) should drop pins for
    both, close the panel, and report the count added."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    def handle_route(route):
        route.fulfill(json=[{
            "display_name": "MG Road, Pune, Maharashtra, India",
            "lat": "18.5204", "lon": "73.8567",
        }])

    page.route("**nominatim.openstreetmap.org/search**", handle_route)
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    page.click("#importBtn")
    page.wait_for_function("document.getElementById('importPanel').style.display === 'flex'")
    page.fill("#importTextarea", "18.5679, 73.7143\nMG Road")
    page.click("#importSubmit")

    page.wait_for_function(
        "document.getElementById('importPanel').style.display === 'none'", timeout=5000,
    )
    n_points = page.evaluate("clickedPoints.length")
    notice = page.inner_text("#notice")
    page.close()
    assert n_points == 2
    assert "Added 2" in notice


def test_bulk_import_reports_lines_it_could_not_place(live_server, browser):
    """When a pasted line can't be geocoded by any query variant, the
    import panel should stay open and say which line failed, rather than
    silently dropping it or closing as if everything succeeded."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.route("**nominatim.openstreetmap.org/search**", lambda route: route.fulfill(json=[]))
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    page.click("#importBtn")
    page.wait_for_function("document.getElementById('importPanel').style.display === 'flex'")
    page.fill("#importTextarea", "Totally Nonexistent Society Zzzqx")
    page.click("#importSubmit")

    page.wait_for_function(
        "document.getElementById('importStatus').textContent.length > 0", timeout=5000,
    )
    status = page.inner_text("#importStatus")
    panel_open = page.eval_on_selector("#importPanel", "el => el.style.display") == "flex"
    page.close()
    assert "Totally Nonexistent Society Zzzqx" in status
    assert panel_open


# ---------- shareable route link ----------

def test_share_button_copies_a_link_that_encodes_the_current_pins_and_settings(live_server, browser):
    """Clicking Share with >=2 pins dropped should copy a URL whose ?r=
    param decodes back to the same pins and the currently-selected
    method/hour/vehicle settings — that round trip is the whole feature."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    # Stub the Clipboard API before any page script runs, so the write is
    # captured deterministically instead of depending on real OS clipboard
    # access (which headless Chromium doesn't reliably grant).
    page.add_init_script("""
        window.__copied = null;
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText: (text) => { window.__copied = text; return Promise.resolve(); } },
        });
    """)
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    page.select_option("#citySelect", "Mumbai")
    page.select_option("#methodSelect", "classical")
    page.click("#map", position={"x": 300, "y": 200})
    page.click("#map", position={"x": 500, "y": 400})
    page.click("#shareBtn")
    page.wait_for_function("window.__copied !== null", timeout=3000)

    copied = page.evaluate("window.__copied")
    page.close()

    assert "?r=" in copied
    encoded = copied.split("?r=", 1)[1]
    state = json.loads(urllib.parse.unquote(encoded))
    assert state["c"] == "Mumbai"
    assert state["m"] == "classical"
    assert len(state["p"]) == 2


def test_opening_a_shared_link_restores_its_pins_and_settings(live_server, browser):
    """The inverse of the above: a URL built by hand with a ?r= state
    should reconstruct the same map on load — city, method, and pins —
    without the visitor having to click anything first."""
    state = {
        "c": "Chennai", "m": "quantum", "h": "18.5", "v": "1", "cap": None,
        "p": [[13.0827, 80.2707], [13.0475, 80.2824], [13.0604, 80.2496]],
    }
    url = f"{live_server}/?r={urllib.parse.quote(json.dumps(state))}"

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(url, wait_until="networkidle", timeout=15000)
    page.wait_for_function("clickedPoints.length === 3", timeout=5000)

    city_value = page.eval_on_selector("#citySelect", "el => el.value")
    method_value = page.eval_on_selector("#methodSelect", "el => el.value")
    notice = page.inner_text("#notice")
    page.close()

    assert city_value == "Chennai"
    assert method_value == "quantum"
    assert "3 stops" in notice


# ---------- GPX + printable itinerary export ----------
# Both exercised by driving lastRouteExport/downloadGpx()/printItinerary()
# directly with synthetic OSRM-shaped data, the same no-real-network
# pattern test_incident_button_renders_for_every_stop_marker_line already
# uses for renderDirections() — a real solve needs a live OSRM call this
# sandbox (and a hermetic test run in general) shouldn't depend on.

_SYNTHETIC_ROUTE_EXPORT_JS = """
    lastRouteExport = {
        points: [[18.52, 73.85], [18.55, 73.90]],
        latlngs: [[18.52, 73.85], [18.53, 73.87], [18.55, 73.90]],
        legs: [{ steps: [
            { maneuver: { type: 'depart' }, name: 'MG Road', distance: 500 },
            { maneuver: { type: 'arrive' }, name: '', distance: 0 },
        ]}],
        cost_minutes: 12.3, free_flow_minutes: 9.1, method: 'quantum', hour: 13,
    };
"""


def test_download_gpx_produces_a_valid_gpx_file_with_waypoints_and_a_track(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.evaluate(_SYNTHETIC_ROUTE_EXPORT_JS)

    with page.expect_download() as dl_info:
        page.evaluate("downloadGpx()")
    content = open(dl_info.value.path()).read()
    page.close()

    assert "<gpx" in content
    assert content.count("<wpt") == 2  # one per point in lastRouteExport.points
    assert "<trkpt" in content  # the road-following geometry, not just the stops


def test_print_itinerary_fills_the_print_area_and_triggers_print(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.evaluate(_SYNTHETIC_ROUTE_EXPORT_JS)
    page.evaluate("window.__printed = false; window.print = () => { window.__printed = true; };")
    page.evaluate("printItinerary()")

    text = page.inner_text("#printArea")
    printed = page.evaluate("window.__printed")
    page.close()

    assert "MG Road" in text
    assert "12.3" in text  # cost_minutes shown in the summary
    assert printed


# ---------- dark / light theme toggle ----------

def test_theme_toggle_switches_theme_and_persists_across_reloads(live_server, browser):
    """Clicking the theme button should flip html[data-theme] (which is
    what every color CSS variable in the stylesheet keys off of), and a
    reload afterward should come back dark — the whole point of persisting
    the choice in localStorage rather than just an in-memory toggle."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    # No stored preference and a headless browser's default OS-level
    # preference is light, so the page should start undecorated (light).
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") is None

    page.click("#themeBtn")
    page.wait_for_function("document.documentElement.getAttribute('data-theme') === 'dark'", timeout=3000)
    page_bg_dark = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--page-bg').trim()"
    )
    moon_visible = page.eval_on_selector("#themeIconMoon", "el => getComputedStyle(el).display") != "none"

    page.reload(wait_until="networkidle")
    theme_after_reload = page.evaluate("document.documentElement.getAttribute('data-theme')")
    page_bg_after_reload = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--page-bg').trim()"
    )
    page.close()

    assert page_bg_dark != ""  # a dark-specific value is actually defined and applied
    assert moon_visible
    assert theme_after_reload == "dark"
    assert page_bg_after_reload == page_bg_dark


def test_theme_toggle_switches_back_to_light(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    page.click("#themeBtn")
    page.wait_for_function("document.documentElement.getAttribute('data-theme') === 'dark'", timeout=3000)
    page.click("#themeBtn")
    page.wait_for_function("document.documentElement.getAttribute('data-theme') !== 'dark'", timeout=3000)
    stored = page.evaluate("localStorage.getItem('routerTheme')")
    sun_visible = page.eval_on_selector("#themeIconSun", "el => getComputedStyle(el).display") != "none"
    page.close()

    assert stored == "light"
    assert sun_visible


def test_theme_toggle_also_swaps_the_street_basemap_tiles(live_server, browser):
    """Regression test for a real reported bug: the theme toggle correctly
    flipped every CSS variable, but with the topbar intentionally dark in
    both themes and no route solved yet (so #stats/#directions are still
    hidden), the only thing a user actually SAW change was the sun/moon
    icon — because the street-view map tiles never had a dark counterpart.
    The fix swaps CARTO Voyager (light) for CARTO Dark Matter (dark) on the
    street basemap whenever the theme changes, so toggling dark mode is
    visibly doing something even before any panel is on screen. Satellite
    view is deliberately excluded (real aerial photography has no honest
    "dark mode"), so this only asserts the street-view swap."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    page.select_option("#basemapSelect", "street")
    page.wait_for_timeout(200)
    assert page.evaluate("map.hasLayer(streetLayer)")
    assert not page.evaluate("map.hasLayer(streetLayerDark)")

    page.click("#themeBtn")
    page.wait_for_function("document.documentElement.getAttribute('data-theme') === 'dark'", timeout=3000)
    assert page.evaluate("map.hasLayer(streetLayerDark)")
    assert not page.evaluate("map.hasLayer(streetLayer)")

    # Satellite view has no dark variant — switching to it under dark theme
    # should show the same imagery layer, not remove basemap coverage.
    page.select_option("#basemapSelect", "satellite")
    page.wait_for_timeout(200)
    assert page.evaluate("map.hasLayer(satelliteLayer)")
    assert not page.evaluate("map.hasLayer(streetLayer)")
    assert not page.evaluate("map.hasLayer(streetLayerDark)")

    # And a dark preference already applied before first paint (a
    # returning visitor, via localStorage) should show dark street tiles
    # immediately on switching to street view, with no extra theme click.
    page.evaluate("localStorage.setItem('routerTheme', 'dark')")
    page.reload(wait_until="networkidle")
    page.select_option("#basemapSelect", "street")
    page.wait_for_timeout(200)
    dark_on_reload = page.evaluate("map.hasLayer(streetLayerDark)")
    page.close()

    assert dark_on_reload


def test_theme_toggle_also_recolors_the_topbar_itself(live_server, browser):
    """Regression test for a real reported bug: with the topbar hardcoded
    to the same dark gradient in both themes, and #stats/#directions still
    hidden before any route is solved, toggling dark mode barely looked
    like it did anything. The fix makes the topbar itself switch between a
    light and a dark skin. This also guards against the exact bug that
    shipped while building that fix: giving the dark-mode dropdown-chevron
    override enough specificity to beat .ghost/.danger's `background:`
    shorthand resurrected a tiled chevron background across every ghost
    button (Import stops, Precedence, Share, Clear points) in dark mode,
    because those buttons' own shorthand still won for background-repeat/
    position (reset to their initial repeating values) while the new rule
    won only for background-image. Real buttons must show no background
    image at all, in either theme — only <select> elements should."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    topbar_bg_light = page.eval_on_selector("#topbar", "el => getComputedStyle(el).backgroundImage")
    topbar_text_light = page.eval_on_selector("#topbar", "el => getComputedStyle(el).color")

    page.click("#themeBtn")
    page.wait_for_function("document.documentElement.getAttribute('data-theme') === 'dark'", timeout=3000)

    topbar_bg_dark = page.eval_on_selector("#topbar", "el => getComputedStyle(el).backgroundImage")
    topbar_text_dark = page.eval_on_selector("#topbar", "el => getComputedStyle(el).color")

    # The regression: real buttons must never pick up a tiled chevron
    # background in either theme — only <select> elements should.
    button_ids = ["#importBtn", "#precedenceBtn", "#clearBtn", "#solveBtn", "#shareBtn", "#themeBtn"]
    button_bg_images_dark = {
        sel: page.eval_on_selector(sel, "el => getComputedStyle(el).backgroundImage.includes('svg+xml')")
        for sel in button_ids
    }
    select_bg_repeat_dark = page.eval_on_selector("#citySelect", "el => getComputedStyle(el).backgroundRepeat")
    page.close()

    assert topbar_bg_light != topbar_bg_dark  # the gradient itself actually differs, not just the icon
    assert topbar_text_light != topbar_text_dark  # dark ink-on-light vs white-on-dark, not the same color
    assert not any(button_bg_images_dark.values()), button_bg_images_dark
    assert select_bg_repeat_dark == "no-repeat"


# ---------- precedence ("visit X before Y") rules panel ----------

def test_precedence_panel_lets_you_add_and_remove_a_rule(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    for x, y in [(200, 200), (300, 200), (400, 200), (500, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 4")

    page.click("#precedenceBtn")
    page.wait_for_function("document.getElementById('precedencePanel').style.display === 'flex'")

    # 4 points -> point 0 is Start, point 3 is End, so only 1 and 2 are
    # eligible interior stops for a rule.
    options = page.eval_on_selector_all("#precUSelect option", "els => els.map(e => e.value)")
    assert options == ["1", "2"]

    page.select_option("#precUSelect", "1")
    page.select_option("#precVSelect", "2")
    page.click("#precAddBtn")
    assert "Stop 1 before Stop 2" in page.inner_text("#precedenceList")
    assert page.evaluate("precedenceRules") == [[1, 2]]

    page.click("#precedenceList button")
    page.wait_for_function("document.getElementById('precedenceList').children.length === 0")
    page.close()
    assert True  # reaching here means the remove click worked


def test_precedence_panel_rejects_duplicate_and_reversed_rules(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    for x, y in [(200, 200), (300, 200), (400, 200), (500, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 4")

    page.click("#precedenceBtn")
    page.wait_for_function("document.getElementById('precedencePanel').style.display === 'flex'")
    page.select_option("#precUSelect", "1")
    page.select_option("#precVSelect", "2")
    page.click("#precAddBtn")

    page.click("#precAddBtn")  # exact duplicate
    assert "already exists" in page.inner_text("#precedenceStatus")

    page.select_option("#precUSelect", "2")
    page.select_option("#precVSelect", "1")
    page.click("#precAddBtn")  # the reverse of the existing rule
    status = page.inner_text("#precedenceStatus")
    rules = page.evaluate("precedenceRules")
    page.close()

    assert "reverse" in status
    assert rules == [[1, 2]]  # neither the duplicate nor the reverse got added


def test_precedence_button_hides_in_fleet_mode(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    assert page.eval_on_selector("#precedenceBtn", "el => getComputedStyle(el).display") != "none"

    page.select_option("#vehicleSelect", "2")
    display = page.eval_on_selector("#precedenceBtn", "el => getComputedStyle(el).display")
    page.close()
    assert display == "none"


def test_precedence_rules_remap_after_a_solve_and_drop_on_stop_removal(live_server, browser):
    """Exercises the two helpers that keep rules pointing at the right
    stops as clickedPoints changes shape — no real solve/network needed,
    same direct-function-call pattern as the other JS-logic tests here."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    remapped = page.evaluate("""
        () => {
            precedenceRules = [[1, 3], [2, 3]];
            _remapPrecedenceAfterSolve([0, 3, 1, 2, 4]); // order[newPos] = oldIdx
            return precedenceRules;
        }
    """)
    assert remapped == [[2, 1], [3, 1]]

    after_removal = page.evaluate("""
        () => {
            precedenceRules = [[1, 4], [2, 5], [5, 6]];
            _removePrecedenceForRemovedIndex(2);
            return precedenceRules;
        }
    """)
    page.close()
    assert after_removal == [[1, 3], [4, 5]]


# ---------- time-window ("arrive between X and Y minutes") rules panel ----------

def test_time_windows_panel_lets_you_add_and_remove_a_rule(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    for x, y in [(200, 200), (300, 200), (400, 200), (500, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 4")

    page.click("#timeWindowsBtn")
    page.wait_for_function("document.getElementById('timeWindowsPanel').style.display === 'flex'")

    # Same eligibility as precedence: point 0 is Start, point 3 is End, so
    # only 1 and 2 are interior stops a window can be attached to.
    options = page.eval_on_selector_all("#twStopSelect option", "els => els.map(e => e.value)")
    assert options == ["1", "2"]

    page.select_option("#twStopSelect", "2")
    page.fill("#twEarliestInput", "10")
    page.fill("#twLatestInput", "25")
    page.click("#twAddBtn")
    assert "Stop 2: 10–25 min" in page.inner_text("#timeWindowsList")
    assert page.evaluate("timeWindows") == {"2": [10, 25]}

    page.click("#timeWindowsList button")
    page.wait_for_function("document.getElementById('timeWindowsList').children.length === 0")
    rules_after_remove = page.evaluate("timeWindows")
    page.close()
    assert rules_after_remove == {}


def test_time_windows_panel_rejects_invalid_ranges(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    for x, y in [(200, 200), (300, 200), (400, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 3")

    page.click("#timeWindowsBtn")
    page.wait_for_function("document.getElementById('timeWindowsPanel').style.display === 'flex'")

    # earliest > latest
    page.fill("#twEarliestInput", "30")
    page.fill("#twLatestInput", "10")
    page.click("#twAddBtn")
    assert "Earliest must be <= latest" in page.inner_text("#timeWindowsStatus")
    assert page.evaluate("timeWindows") == {}

    # missing latest entirely
    page.fill("#twEarliestInput", "5")
    page.fill("#twLatestInput", "")
    page.click("#twAddBtn")
    status = page.inner_text("#timeWindowsStatus")
    rules = page.evaluate("timeWindows")
    page.close()
    assert "Enter both" in status
    assert rules == {}


def test_time_windows_button_hides_in_fleet_mode(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    assert page.eval_on_selector("#timeWindowsBtn", "el => getComputedStyle(el).display") != "none"

    page.select_option("#vehicleSelect", "2")
    display = page.eval_on_selector("#timeWindowsBtn", "el => getComputedStyle(el).display")
    page.close()
    assert display == "none"


def test_time_windows_remap_after_a_solve_and_drop_on_stop_removal(live_server, browser):
    """Same direct-function-call pattern as the precedence remap/drop test
    above: exercise _remapTimeWindowsAfterSolve and
    _removeTimeWindowForRemovedIndex with synthetic state, no real
    solve/network needed."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    remapped = page.evaluate("""
        () => {
            timeWindows = {1: [5, 15], 3: [20, 30]};
            _remapTimeWindowsAfterSolve([0, 3, 1, 2, 4]); // order[newPos] = oldIdx
            return timeWindows;
        }
    """)
    assert remapped == {"2": [5, 15], "1": [20, 30]}

    after_removal = page.evaluate("""
        () => {
            timeWindows = {1: [5, 15], 2: [20, 30], 5: [40, 50]};
            _removeTimeWindowForRemovedIndex(2);
            return timeWindows;
        }
    """)
    page.close()
    assert after_removal == {"1": [5, 15], "4": [40, 50]}


# ---------- per-stop weights (fleet mode "Max load/vehicle") ----------

def test_weights_button_only_appears_in_fleet_mode_with_weighted_capacity(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    # single-vehicle mode: capacityWrap (and weightsBtn inside it) is hidden entirely
    assert page.eval_on_selector("#capacityWrap", "el => getComputedStyle(el).display") == "none"

    page.select_option("#vehicleSelect", "2")
    assert page.eval_on_selector("#weightsBtn", "el => getComputedStyle(el).display") == "none"

    page.select_option("#capacityModeSelect", "weight")
    display = page.eval_on_selector("#weightsBtn", "el => getComputedStyle(el).display")
    page.close()
    assert display != "none"


def test_weights_panel_lists_every_current_stop_and_saves_edits(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.select_option("#vehicleSelect", "2")
    page.select_option("#capacityModeSelect", "weight")

    for x, y in [(200, 200), (300, 200), (400, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 3")

    page.click("#weightsBtn")
    page.wait_for_function("document.getElementById('weightsPanel').style.display === 'flex'")

    # point 0 is the depot in fleet mode; 1 and 2 are the (only) real stops
    rows = page.eval_on_selector_all("#weightsList li input", "els => els.map(e => e.dataset.idx)")
    assert rows == ["1", "2"]

    page.fill("#weightsList input[data-idx='2']", "25")
    page.eval_on_selector("#weightsList input[data-idx='2']", "el => el.dispatchEvent(new Event('input'))")
    weights = page.evaluate("stopWeights")
    page.close()
    assert weights == {"2": 25}


def test_stop_weight_helper_drops_removed_index_and_shifts_others(live_server, browser):
    """Same direct-function-call pattern as the precedence remap/drop test
    above: exercise _removeWeightForRemovedIndex with synthetic stopWeights
    state, no real map interaction needed."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    after_removal = page.evaluate("""
        () => {
            stopWeights = {1: 10, 2: 20, 3: 30};
            _removeWeightForRemovedIndex(2);
            return stopWeights;
        }
    """)
    page.close()
    assert after_removal == {"1": 10, "2": 30}


# ---------- "Live re-optimize" continuous re-optimization demo ----------
# See README.md's "Continuous re-optimization" section and
# templates/click_router.html's own "Live re-optimization demo" comment
# block for the full honest scope: a simulated clock advancing on a timer,
# repeatedly calling the SAME /api/solve endpoint the manual "Solve route"
# and "Simulate incident" buttons use. These tests exercise that through a
# real browser against the real running app.py (not the Flask test
# client) — /api/solve itself is reached at live_server's own local
# address and is NOT stubbed, only the external OSRM/tile services this
# sandbox can't reach are, so this verifies the real backend end-to-end,
# just substituting the external routing/tile services.

def _stub_map_tiles(page):
    """Abort real map-tile requests outright — irrelevant to what these
    tests check, and, against real external tile hosts, slow/unreliable to
    wait on in a network-restricted environment. Leaflet tolerates failed
    tile loads fine (it just shows blank tiles), so this doesn't affect
    any of the JS behavior under test."""
    page.route("**basemaps.cartocdn.com/**", lambda route: route.abort())
    page.route("**arcgisonline.com/**", lambda route: route.abort())


def _stub_osrm(page, n_points):
    """Fulfil OSRM's Table and Route APIs with a small synthetic road
    network so a real click -> solve -> draw flow can run in a browser
    with no real network access to router.project-osrm.org."""
    def handle_table(route):
        durations = [
            [0 if i == j else 300 + 60 * abs(i - j) for j in range(n_points)]
            for i in range(n_points)
        ]
        route.fulfill(json={"code": "Ok", "durations": durations})

    def handle_route_geom(route):
        route.fulfill(json={
            "code": "Ok",
            "routes": [{
                "geometry": {"coordinates": [[77.55, 12.90], [77.60, 12.95]]},
                "distance": 5000,
                "duration": 600,
                "legs": [
                    {"steps": [
                        {"maneuver": {"type": "depart"}, "name": "Test Road", "distance": 500},
                        {"maneuver": {"type": "arrive"}, "name": "", "distance": 0},
                    ]}
                    for _ in range(max(1, n_points - 1))
                ],
            }],
        })

    page.route("**router.project-osrm.org/table/**", handle_table)
    page.route("**router.project-osrm.org/route/**", handle_route_geom)


def _solve_three_stops(page):
    """Programmatically drop 3 points and solve — bypassing real map
    clicks (which need real tile-rendered pixel coordinates) the same way
    other tests in this file call internal JS functions directly."""
    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.93, 77.62); addPoint(12.91, 77.63); }
    """)
    page.click("#solveBtn")
    page.wait_for_function("document.getElementById('stats').style.display === 'block'", timeout=10000)


def test_live_reopt_button_only_enables_after_a_successful_solve(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    disabled_before = page.eval_on_selector("#liveReoptBtn", "el => el.disabled")
    _solve_three_stops(page)
    disabled_after = page.eval_on_selector("#liveReoptBtn", "el => el.disabled")

    page.close()
    assert disabled_before is True
    assert disabled_after is False


def test_live_reopt_start_logs_a_tick_and_stop_resets_the_button(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    _solve_three_stops(page)

    page.click("#liveReoptBtn")
    # Wait for the SECOND feed line, not just the first: the first line is
    # the synchronous "live re-optimization started" notice, appended
    # before the first real tick's (async) /api/solve round-trip
    # completes.
    page.wait_for_function(
        "document.getElementById('liveFeed-list').children.length > 1", timeout=10000,
    )
    is_active = page.eval_on_selector("#liveReoptBtn", "el => el.classList.contains('live-active')")
    feed_text = page.inner_text("#liveFeed-list")

    page.click("#liveReoptBtn")  # stop
    page.wait_for_function(
        "!document.getElementById('liveReoptBtn').classList.contains('live-active')", timeout=5000,
    )
    stopped_label = page.inner_text("#liveReoptBtn")
    is_active_after_stop = page.eval_on_selector("#liveReoptBtn", "el => el.classList.contains('live-active')")

    page.close()
    assert is_active is True
    assert "min" in feed_text  # a real tick logged a cost figure, not an empty/placeholder line
    assert is_active_after_stop is False
    assert "Live re-optimize" in stopped_label


def test_live_reopt_stops_and_disables_when_points_are_cleared(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    _solve_three_stops(page)

    page.click("#liveReoptBtn")
    page.wait_for_function(
        "document.getElementById('liveFeed-list').children.length > 0", timeout=10000,
    )
    page.click("#clearBtn")

    is_active_after_clear = page.eval_on_selector("#liveReoptBtn", "el => el.classList.contains('live-active')")
    disabled_after_clear = page.eval_on_selector("#liveReoptBtn", "el => el.disabled")

    page.close()
    assert is_active_after_clear is False
    assert disabled_after_clear is True


def test_live_reopt_works_in_fleet_mode_and_ticks_without_crashing(live_server, browser):
    """Fleet-mode support in _liveReoptTickFleet() previously had only
    unit-level coverage (fleetOrderChanged in tests/frontend/) and Flask-
    test-client coverage of /api/solve_fleet's new incident_pairs field —
    this exercises the actual dispatch (liveReoptTick() picking the fleet
    tick over the single-vehicle one) end-to-end through a real browser,
    the same way the single-vehicle tests above do."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 4)
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    page.select_option("#vehicleSelect", "2")
    page.evaluate("""
        () => {
            addPoint(12.97, 77.59); addPoint(12.93, 77.62);
            addPoint(12.91, 77.63); addPoint(12.90, 77.65);
        }
    """)
    page.click("#solveBtn")
    page.wait_for_function("document.getElementById('stats').style.display === 'block'", timeout=10000)
    disabled_after_fleet_solve = page.eval_on_selector("#liveReoptBtn", "el => el.disabled")

    page.click("#liveReoptBtn")
    page.wait_for_function(
        "document.getElementById('liveFeed-list').children.length > 1", timeout=10000,
    )
    is_active = page.eval_on_selector("#liveReoptBtn", "el => el.classList.contains('live-active')")
    feed_text = page.inner_text("#liveFeed-list")

    page.click("#liveReoptBtn")  # stop
    page.wait_for_function(
        "!document.getElementById('liveReoptBtn').classList.contains('live-active')", timeout=5000,
    )
    page.close()

    assert disabled_after_fleet_solve is False  # Live re-optimize is no longer fleet-disabled
    assert is_active is True
    assert "min" in feed_text  # a real fleet re-solve logged a real cost figure


# ---------- Method comparison panel ----------

def test_compare_button_enabled_state_tracks_point_count_and_fleet_mode(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    disabled_with_no_points = page.eval_on_selector("#compareBtn", "el => el.disabled")
    page.evaluate("() => { addPoint(12.97, 77.59); addPoint(12.93, 77.62); }")
    disabled_with_two_points = page.eval_on_selector("#compareBtn", "el => el.disabled")

    page.select_option("#vehicleSelect", "2")
    disabled_in_fleet_mode = page.eval_on_selector("#compareBtn", "el => el.disabled")
    page.select_option("#vehicleSelect", "1")
    disabled_after_back_to_single = page.eval_on_selector("#compareBtn", "el => el.disabled")

    page.close()
    assert disabled_with_no_points is True
    assert disabled_with_two_points is False
    assert disabled_in_fleet_mode is True
    assert disabled_after_back_to_single is False


def test_compare_methods_draws_both_routes_and_shows_a_side_by_side_table(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.evaluate(
        "() => { addPoint(12.97, 77.59); addPoint(12.93, 77.62); addPoint(12.91, 77.63); }"
    )

    page.click("#compareBtn")
    page.wait_for_function(
        "document.getElementById('compareContent').textContent.includes('Drive time')", timeout=10000,
    )

    panel_visible = page.eval_on_selector("#comparePanel", "el => getComputedStyle(el).display") == "flex"
    content_text = page.inner_text("#compareContent")
    layer_count = page.evaluate("compareRouteLayer ? compareRouteLayer.getLayers().length : 0")
    # main routeLayer/lastSolveContext must be untouched — comparing is
    # deliberately non-committing, unlike a real "Solve route" click.
    last_solve_context = page.evaluate("lastSolveContext")

    page.close()
    assert panel_visible
    assert "min" in content_text
    assert layer_count >= 2  # one polyline per method
    assert last_solve_context is None


def test_compare_methods_omits_time_windows_from_the_classical_request_only(live_server, browser):
    """Classical has no notion of a position constraint (see app.py's
    _validate_time_windows) — sending time_windows on that side would 400
    and kill the whole comparison, so compareMethods() must send it only
    on the quantum-inspired request. Verified by intercepting both
    /api/solve calls and inspecting their actual JSON bodies, not just
    trusting the UI didn't show an error."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(live_server, wait_until="networkidle", timeout=15000)
    page.evaluate(
        "() => { addPoint(12.97, 77.59); addPoint(12.93, 77.62); addPoint(12.91, 77.63); }"
    )
    page.evaluate("() => { timeWindows[1] = [5, 20]; }")

    page.evaluate("""
        () => {
            window.__solveBodies = [];
            const realFetch = window.fetch;
            window.fetch = (url, opts) => {
                if (typeof url === 'string' && url.includes('/api/solve') && !url.includes('_fleet')) {
                    window.__solveBodies.push(JSON.parse(opts.body));
                }
                return realFetch(url, opts);
            };
        }
    """)
    page.click("#compareBtn")
    page.wait_for_function("window.__solveBodies && window.__solveBodies.length === 2", timeout=10000)
    bodies = page.evaluate("window.__solveBodies")
    page.close()

    by_method = {b["method"]: b for b in bodies}
    assert by_method["quantum"]["time_windows"] == {"1": [5, 20]}
    assert by_method["classical"]["time_windows"] == {}
