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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Fleet select now lives in the Options drawer
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Fleet/capacity controls now live in the Options drawer

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # every info-icon *inside the drawer* lives there;
    # the topbar's own PS-Alignment badge has an independent info-icon, so scope
    # this locator to the drawer rather than the bare `.info-icon` class.

    icon = page.locator("#optionsDrawer .info-icon").first
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # scope to the drawer: the topbar's PS-Alignment
    # badge has its own separate info-icon, and is hidden at this narrow width.
    page.locator("#optionsDrawer .info-icon").first.click()
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Import stops now lives in the Options drawer

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Import stops now lives in the Options drawer

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Method select and Share now live in the Options drawer

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
    url = f"{live_server}/app?r={urllib.parse.quote(json.dumps(state))}"

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    # Stub real map tiles — this test doesn't care what's drawn under the
    # pins, only that they got restored, and letting "networkidle" wait on
    # real (possibly slow/blocked-in-sandbox) tile requests risks the
    # restore notice's own auto-dismiss timer (~4.2s) elapsing before this
    # test gets a chance to read it.
    _stub_map_tiles(page)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

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
    The fix swaps a light gray-canvas basemap for a dark gray-canvas one on
    the street basemap whenever the theme changes, so toggling dark mode is
    visibly doing something even before any panel is on screen. Satellite
    view is deliberately excluded (real aerial photography has no honest
    "dark mode"), so this only asserts the street-view swap.

    Needs real network access to server.arcgisonline.com for both
    streetLayer and streetLayerDark now (previously only satelliteLayer did) —
    still the one test in this file that can't run in a network-restricted
    sandbox; unrelated to whichever basemap provider is behind the scenes."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Map view (basemap select) now lives in the Options drawer

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
    page.click("#optionsBtn")  # drawer resets closed on reload
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    for x, y in [(200, 200), (300, 200), (400, 200), (500, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 4")

    page.click("#optionsBtn")  # Precedence now lives in the Options drawer
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    for x, y in [(200, 200), (300, 200), (400, 200), (500, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 4")

    page.click("#optionsBtn")  # Precedence now lives in the Options drawer
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


def test_precedence_button_and_rules_work_in_fleet_mode_too(live_server, browser):
    """Cross-cluster precedence (product-audit item): precedence used to be
    single-vehicle-mode only in the UI, hidden and cleared the moment you
    switched to fleet mode. It's now available in both — the button stays
    visible, an existing rule survives the mode switch, and the eligible-
    stop range widens to include every non-depot stop (fleet mode has no
    fixed "End", only a Depot at index 0)."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    for x, y in [(200, 200), (300, 200), (400, 200), (500, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 4")

    page.click("#optionsBtn")  # Precedence/Fleet now live in the Options drawer
    page.click("#precedenceBtn")
    page.wait_for_function("document.getElementById('precedencePanel').style.display === 'flex'")
    page.select_option("#precUSelect", "1")
    page.select_option("#precVSelect", "2")
    page.click("#precAddBtn")
    assert page.evaluate("precedenceRules") == [[1, 2]]

    page.select_option("#vehicleSelect", "2")  # switch into fleet mode
    assert page.eval_on_selector("#precedenceBtn", "el => getComputedStyle(el).display") != "none"
    assert page.evaluate("precedenceRules") == [[1, 2]]  # the rule survives the mode switch

    page.click("#precedenceBtn")
    page.wait_for_function("document.getElementById('precedencePanel').style.display === 'flex'")
    # Fleet mode: point 0 is the Depot, everything else is an eligible stop —
    # including index 3, which would have been the fixed "End" before.
    options = page.eval_on_selector_all("#precUSelect option", "els => els.map(e => e.value)")
    assert options == ["1", "2", "3"]
    page.close()


def test_fleet_solve_with_precedence_is_satisfied_end_to_end(live_server, browser):
    """Cross-cluster precedence + precedence-in-fleet-mode (product-audit
    items), exercised through the real backend (only OSRM is stubbed —
    /api/solve_fleet itself is never mocked): a precedence rule that the
    fleet split may well put on two different vehicles at first must still
    come back satisfied, with the "Why this route?" panel showing the
    checkmark, not a violated row."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 5)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Method/Fleet select now live in the Options drawer
    page.select_option("#methodSelect", "classical")
    page.select_option("#vehicleSelect", "3")
    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62); addPoint(12.90, 77.63); }
    """)

    page.click("#precedenceBtn")
    page.wait_for_function("document.getElementById('precedencePanel').style.display === 'flex'")
    page.select_option("#precUSelect", "1")
    page.select_option("#precVSelect", "4")
    page.click("#precAddBtn")
    page.click("#precedenceClose")

    page.click("#solveBtn")
    page.wait_for_function("document.getElementById('stats').style.display === 'block'", timeout=10000)

    stats_html = page.inner_html("#stats")
    page.close()
    assert "before" in stats_html
    assert "violated" not in stats_html  # the rule must actually be satisfied, not just attempted


def test_precedence_impact_button_shows_a_real_before_after_comparison(live_server, browser):
    """Product-audit item: explain_open_path_precedence_impact (src/explain.py)
    used to exist only as a tested library function, never reachable from
    the UI. Exercised through the real backend end-to-end: adding a
    precedence rule reveals the "What does this rule cost me?" button, and
    clicking it shows a genuine before/after cost comparison."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 4)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Method select now lives in the Options drawer
    page.select_option("#methodSelect", "classical")
    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62); }
    """)

    page.click("#precedenceBtn")
    page.wait_for_function("document.getElementById('precedencePanel').style.display === 'flex'")
    assert page.eval_on_selector("#precImpactBtn", "el => getComputedStyle(el).display") == "none"

    page.select_option("#precUSelect", "1")
    page.select_option("#precVSelect", "2")
    page.click("#precAddBtn")
    assert page.eval_on_selector("#precImpactBtn", "el => getComputedStyle(el).display") != "none"

    page.click("#precImpactBtn")
    page.wait_for_function(
        "document.getElementById('precedenceImpact').textContent.includes('Real extra cost')", timeout=10000,
    )
    impact_text = page.inner_text("#precedenceImpact")
    page.close()
    assert "Without this rule" in impact_text
    assert "With this rule" in impact_text
    assert "min" in impact_text


def test_precedence_rules_remap_after_a_solve_and_drop_on_stop_removal(live_server, browser):
    """Exercises the two helpers that keep rules pointing at the right
    stops as clickedPoints changes shape — no real solve/network needed,
    same direct-function-call pattern as the other JS-logic tests here."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    for x, y in [(200, 200), (300, 200), (400, 200), (500, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 4")

    page.click("#optionsBtn")  # Time windows now lives in the Options drawer
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    for x, y in [(200, 200), (300, 200), (400, 200)]:
        page.click("#map", position={"x": x, "y": y})
    page.wait_for_function("clickedPoints.length === 3")

    page.click("#optionsBtn")  # Time windows now lives in the Options drawer
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Time windows/Fleet now live in the Options drawer
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Fleet/capacity controls now live in the Options drawer

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Fleet/capacity controls now live in the Options drawer
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

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
# See docs/live-app.md's "Continuous re-optimization" section and
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
    any of the JS behavior under test. Both satellite and street basemaps
    are served from arcgisonline.com now (see templates/click_router.html's
    streetLayer/streetLayerDark — CARTO's basemaps.cartocdn.com used to be
    the street one, until CARTO started requiring an API key), so aborting
    that one host covers both."""
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Live re-optimize now lives in the Options drawer
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Live re-optimize now lives in the Options drawer
    _solve_three_stops(page)

    page.click("#liveReoptBtn")
    page.wait_for_function(
        "document.getElementById('liveFeed-list').children.length > 0", timeout=10000,
    )
    # A solved route exists here, so Clear now arms a "click again to
    # confirm" state on its first click (see the confirm-before-clear
    # feature added to click_router.html) rather than clearing immediately
    # — two clicks are needed to actually confirm the destructive action.
    page.click("#clearBtn")
    page.wait_for_selector("#clearBtn.confirm-armed")
    page.click("#clearBtn")

    is_active_after_clear = page.eval_on_selector("#liveReoptBtn", "el => el.classList.contains('live-active')")
    disabled_after_clear = page.eval_on_selector("#liveReoptBtn", "el => el.disabled")

    page.close()
    assert is_active_after_clear is False
    assert disabled_after_clear is True


def test_clear_wipes_immediately_when_nothing_would_be_lost(live_server, browser):
    """The confirm-armed state (see the test above) exists specifically to
    protect a solved route / rules / weights — it should NOT get in the
    way of the common case of clearing an empty or barely-started map."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    page.evaluate("() => { addPoint(12.97, 77.59); }")  # one pin, never solved
    page.click("#clearBtn")

    n_points_after = page.evaluate("() => clickedPoints.length")
    armed_after = page.eval_on_selector("#clearBtn", "el => el.classList.contains('confirm-armed')")

    page.close()
    assert n_points_after == 0
    assert armed_after is False


def test_confirm_armed_clear_button_disarms_itself_after_a_timeout(live_server, browser):
    """A first click that arms the button but is never followed up on
    should quietly revert on its own, rather than leave a stale "click
    again to confirm" label sitting on the button forever."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    _solve_three_stops(page)

    page.click("#clearBtn")
    page.wait_for_selector("#clearBtn.confirm-armed")
    page.wait_for_selector("#clearBtn:not(.confirm-armed)", timeout=6000)  # the 4s arm timer expiring

    n_points_still_there = page.evaluate("() => clickedPoints.length")

    page.close()
    assert n_points_still_there == 3  # never actually cleared — the second click never came


def test_stats_strip_loads_real_analytics_numbers(live_server, browser):
    """Product-audit Quick Win #1: /api/analytics was fully built and
    tested server-side but never surfaced anywhere in the UI. This checks
    the live stats strip actually replaces its placeholder text with a
    real number from that endpoint, not that it gets stuck on
    "Loading live stats..." forever."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    page.wait_for_function(
        "!document.getElementById('statsStripText').textContent.includes('Loading')", timeout=10000,
    )
    text = page.inner_text("#statsStripText")

    page.close()
    assert "Loading" not in text
    assert "solve" in text.lower() or "deployment" in text.lower()


def test_insights_panel_opens_and_renders_real_benchmark_charts(live_server, browser):
    """Product-audit Major Feature #1: the honest benchmark finding
    (classical wins on plain routing, quantum-inspired wins once a real
    constraint is added) should be visible INSIDE the product, not just
    in a README. This runs against the real app.py subprocess with this
    checkout's actual output/*.csv files, so a rendered "Experiment 1"
    card here means /api/insights served real data end to end, not a
    mock."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    page.evaluate("() => openInsightsPanel()")
    page.wait_for_function(
        "document.getElementById('insightsCharts').querySelectorAll('.insight-card').length > 0", timeout=10000,
    )
    panel_visible = page.eval_on_selector("#insightsPanel", "el => getComputedStyle(el).display")
    charts_text = page.inner_text("#insightsCharts")

    page.close()
    assert panel_visible == "flex"
    assert "Experiment 1" in charts_text
    assert "Experiment 2" in charts_text


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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Fleet select and Live re-optimize now live in the Options drawer

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.click("#optionsBtn")  # Fleet/Compare controls now live in the Options drawer

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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.evaluate(
        "() => { addPoint(12.97, 77.59); addPoint(12.93, 77.62); addPoint(12.91, 77.63); }"
    )

    page.click("#optionsBtn")  # Compare methods now lives in the Options drawer
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
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
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
    page.click("#optionsBtn")  # Compare methods now lives in the Options drawer
    page.click("#compareBtn")
    page.wait_for_function("window.__solveBodies && window.__solveBodies.length === 2", timeout=10000)
    bodies = page.evaluate("window.__solveBodies")
    page.close()

    by_method = {b["method"]: b for b in bodies}
    assert by_method["quantum"]["time_windows"] == {"1": [5, 20]}
    assert by_method["classical"]["time_windows"] == {}


# ---------- Route History & Favorites ("My Routes" panel) ----------
# Product-audit Major Feature #2. Backend: none — everything here is
# localStorage, so these tests drive the real browser storage the same
# way a real visitor's would persist, with no server involved beyond the
# one real /api/solve round trip in the first test.

def test_history_records_a_solved_route_and_reloads_it_after_clearing(live_server, browser):
    """A real solve should append a localStorage entry with the right
    shape, and — the actual point of the feature — clicking Load in the
    My Routes panel after the map has been cleared should bring the same
    pins and city back, exactly like opening a shared link does."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.select_option("#citySelect", "Chennai")
    _solve_three_stops(page)

    history = page.evaluate("JSON.parse(localStorage.getItem('routerHistory'))")
    assert len(history) == 1
    assert history[0]["stops"] == 3
    assert history[0]["mode"] == "single"
    assert history[0]["state"]["c"] == "Chennai"
    assert history[0]["favorite"] is False

    # Clear the map (two clicks: the confirm-armed pattern, since a solved
    # route is "something to lose") so Load has something real to prove.
    page.click("#clearBtn")
    page.wait_for_selector("#clearBtn.confirm-armed")
    page.click("#clearBtn")
    page.wait_for_function("clickedPoints.length === 0")

    page.click("#optionsBtn")
    page.click("#historyBtn")
    page.wait_for_function("document.getElementById('historyPanel').style.display === 'flex'")
    page.click("#historyList .history-load")
    page.wait_for_function("clickedPoints.length === 3", timeout=5000)

    city_after_load = page.eval_on_selector("#citySelect", "el => el.value")
    panel_closed = page.eval_on_selector("#historyPanel", "el => el.style.display") == "none"
    page.close()
    assert city_after_load == "Chennai"
    assert panel_closed


def test_history_star_toggles_favorite_and_delete_removes_the_entry(live_server, browser):
    """Exercises the star/delete controls directly against a synthetic
    entry (no real solve needed — same direct-function-call pattern the
    precedence/time-window remap tests above use) so this doesn't depend
    on a real OSRM round trip to check UI wiring."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    page.evaluate("""
        () => {
            addPoint(12.97, 77.59); addPoint(12.93, 77.62);
            _recordHistoryEntry({ mode: 'single', costMinutes: 42, savingsPct: 10 });
        }
    """)
    page.click("#optionsBtn")
    page.click("#historyBtn")
    page.wait_for_function("document.getElementById('historyList').children.length === 1")

    page.click(".history-star")
    favorite_after_star = page.evaluate(
        "JSON.parse(localStorage.getItem('routerHistory'))[0].favorite"
    )
    assert favorite_after_star is True
    assert "active" in (page.get_attribute(".history-star", "class") or "")

    page.click(".history-delete")
    page.wait_for_selector("#historyList .history-empty")  # real entry gone, empty-state placeholder shown instead
    remaining = page.evaluate("JSON.parse(localStorage.getItem('routerHistory'))")
    page.close()
    assert remaining == []


def test_history_never_evicts_a_favorited_entry_past_the_unstarred_cap(live_server, browser):
    """The eviction cap only ever trims UNSTARRED entries — a starred
    route has to survive no matter how many newer solves pile up after
    it, since the whole point of starring one is "keep this forever"."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    cap = page.evaluate("_HISTORY_MAX_UNSTARRED")  # read the real constant, don't duplicate it here

    result = page.evaluate("""
        () => {
            const seed = [];
            for (let i = 0; i < _HISTORY_MAX_UNSTARRED + 5; i++) {
                seed.push({
                    id: `seed-${i}`, savedAt: Date.now() - i, favorite: false,
                    state: { c: 'Pune', m: 'quantum', h: 'now', v: '1', cap: null, cm: 'count', p: [[18.5, 73.8]], prec: [], tw: {}, w: {} },
                    mode: 'single', vehicles: null, costMinutes: 10, savingsPct: 5, stops: 1,
                });
            }
            seed[seed.length - 1].favorite = true; // the OLDEST entry is starred
            localStorage.setItem('routerHistory', JSON.stringify(seed));

            addPoint(12.97, 77.59); addPoint(12.93, 77.62);
            _recordHistoryEntry({ mode: 'single', costMinutes: 99, savingsPct: 1 }); // one more solve triggers the trim

            const after = JSON.parse(localStorage.getItem('routerHistory'));
            return {
                total: after.length,
                favoritedStillThere: after.some(e => e.id === `seed-${_HISTORY_MAX_UNSTARRED + 4}`),
                unstarredCount: after.filter(e => !e.favorite).length,
            };
        }
    """)
    page.close()
    assert result["favoritedStillThere"] is True
    assert result["unstarredCount"] == cap
    assert result["total"] == cap + 1  # the cap's worth of unstarred entries, plus the one favorite


# ---------- Landing page + first-run tour (Major #4) ----------
# The live app itself gates its onboarding tour behind `!navigator.webdriver`
# (see the `_maybeStartTour` IIFE at the bottom of click_router.html) so it
# doesn't pop up uninvited over every other test in this file, which all run
# against a fresh, empty-localStorage page the same way a genuine first-time
# visitor would arrive. These tests are the deliberate exception: they spoof
# `navigator.webdriver` back to `false` before navigating, so they exercise
# the exact code path a real first-time visitor hits.

def _allow_tour(page):
    """Undo Playwright's navigator.webdriver=true for this page, so the
    tour's automation guard doesn't also suppress it here — the one place
    that guard should NOT apply."""
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")


def test_landing_page_links_to_the_live_app_and_the_static_demo(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(live_server, wait_until="networkidle", timeout=15000)

    heading_visible = page.is_visible("h1")
    app_card_href = page.eval_on_selector("#cards a:nth-of-type(1)", "el => el.getAttribute('href')")
    demo_card_href = page.eval_on_selector("#cards a:nth-of-type(2)", "el => el.getAttribute('href')")

    page.click("#cards a:nth-of-type(1)")
    page.wait_for_selector("#topbar", timeout=15000)
    landed_on_live_app = "/app" in page.url

    page.close()
    assert heading_visible
    assert app_card_href == "/app"
    assert demo_card_href == "/demo"
    assert landed_on_live_app


def test_brand_link_in_live_app_returns_to_the_landing_page(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    page.click("#brand")
    page.wait_for_selector("#cards", timeout=15000)
    back_on_landing = page.url.rstrip("/") == live_server.rstrip("/")

    page.close()
    assert back_on_landing


def test_first_run_tour_appears_for_a_fresh_visitor_and_advances_on_real_actions(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _allow_tour(page)
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    # Step 1: shown immediately to an empty-state visitor, pointing them at
    # the map rather than a specific element.
    page.wait_for_selector("#tourCallout.visible", timeout=5000)
    assert "Click anywhere on the map" in page.inner_text("#tourText")

    # Step 2: advances only once 2 points exist — not on the first point.
    # (textContent, not inner_text — the label is CSS text-transform:
    # uppercase, which inner_text renders as "STEP 1 OF 3".)
    page.evaluate("() => addPoint(12.97, 77.59)")
    still_step_1 = "Step 1 of 3" == page.eval_on_selector("#tourStepLabel", "el => el.textContent")
    page.evaluate("() => addPoint(12.93, 77.62)")
    page.wait_for_function("document.getElementById('tourStepLabel').textContent === 'Step 2 of 3'", timeout=5000)
    step_2_points_at_solve = page.eval_on_selector(
        "#tourCallout", "el => el.style.display"
    ) == "flex"

    # A 3rd point to match _stub_osrm's 3x3 synthetic matrix above (the
    # tour itself only cares that >= 2 points exist for this step).
    page.evaluate("() => addPoint(12.91, 77.63)")

    # Step 3: advances on a successful solve, pointing at the incident button.
    page.click("#solveBtn")
    page.wait_for_function("document.getElementById('stats').style.display === 'block'", timeout=10000)
    page.wait_for_function("document.getElementById('tourStepLabel').textContent === 'Step 3 of 3'", timeout=5000)
    step_3_text = page.inner_text("#tourText")

    # Dismissing persists, so a reload never shows it again.
    page.click("#tourDismiss")
    dismissed_key = page.evaluate("localStorage.getItem('routerTourDismissed')")

    page.close()
    assert still_step_1
    assert step_2_points_at_solve
    assert "Simulate incident" in step_3_text
    assert dismissed_key == "1"


def test_first_run_tour_never_reappears_once_dismissed(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _allow_tour(page)
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.wait_for_selector("#tourCallout.visible", timeout=5000)

    page.click("#tourDismiss")
    page.reload(wait_until="networkidle")
    # Give any (incorrect) re-trigger a moment to show up before asserting absence.
    page.wait_for_timeout(300)
    tour_visible_after_reload = page.eval_on_selector(
        "#tourCallout", "el => el.classList.contains('visible')"
    )

    page.close()
    assert tour_visible_after_reload is False


def test_first_run_tour_skips_a_visitor_who_already_has_state(live_server, browser):
    """A shared link (or any other path that arrives with points already on
    the map) is not a first-time visit — showing "click anywhere to start"
    to someone who already has a route loaded would be actively wrong."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _allow_tour(page)
    _stub_map_tiles(page)
    state = {
        "c": "Bengaluru", "m": "quantum", "h": "now", "v": "1", "cap": None, "cm": "count",
        "p": [[12.97, 77.59], [12.93, 77.62]], "prec": [], "tw": {}, "w": {},
    }
    url = f"{live_server}/app?r={urllib.parse.quote(json.dumps(state))}"
    page.goto(url, wait_until="networkidle", timeout=15000)
    page.wait_for_function("clickedPoints.length === 2", timeout=5000)
    page.wait_for_timeout(300)  # let a (incorrect) tour trigger have its chance before asserting absence

    tour_visible = page.eval_on_selector("#tourCallout", "el => el.classList.contains('visible')")

    page.close()
    assert tour_visible is False


# ---------- On-map constraint annotations (Wow #6) ----------
# A dashed pink connector between an active precedence pair's pins, and a
# small clock badge on any pin with a time-window rule — see
# _redrawPrecedenceConnectors() and pinIcon() in click_router.html. Both
# are purely visual (no new request/response shape), so these tests drive
# the same internal functions the precedence/time-window panel tests above
# use, then check the actual Leaflet layer / DOM state rather than any
# network call.

def test_precedence_rule_draws_a_dashed_connector_between_its_two_pins(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    # 4 points -> 2 interior stops (indices 1, 2), the minimum the
    # precedence form needs to offer two different stops.
    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62); }
    """)
    page.click("#optionsBtn")
    page.click("#precedenceBtn")
    page.select_option("#precUSelect", "1")
    page.select_option("#precVSelect", "2")
    page.click("#precAddBtn")

    connector_count = page.evaluate("precedenceLayer.getLayers().length")
    connector_style = page.evaluate("""
        () => {
            const layer = precedenceLayer.getLayers()[0];
            return { color: layer.options.color, dashArray: layer.options.dashArray };
        }
    """)

    # Removing the rule from the panel clears the connector.
    page.click("#precedenceList button")
    connector_count_after_remove = page.evaluate("precedenceLayer.getLayers().length")

    page.close()
    assert connector_count == 1
    assert connector_style["color"] == "#ec4899"
    assert connector_style["dashArray"]
    assert connector_count_after_remove == 0


def test_removing_a_pin_in_a_precedence_rule_clears_its_connector(live_server, browser):
    """_removePrecedenceForRemovedIndex already drops any rule naming a
    removed stop — this checks the on-map connector actually follows that,
    not just the rule list."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    page.evaluate("""
        () => {
            addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62);
            precedenceRules.push([1, 2]);
            _renderPrecedenceList();
        }
    """)
    connector_count_before = page.evaluate("precedenceLayer.getLayers().length")

    page.evaluate("() => removePoint(1)")  # removes one end of the rule
    connector_count_after = page.evaluate("precedenceLayer.getLayers().length")

    page.close()
    assert connector_count_before == 1
    assert connector_count_after == 0


def test_time_window_rule_shows_a_clock_badge_on_its_pin(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); }
    """)
    page.click("#optionsBtn")
    page.click("#timeWindowsBtn")
    page.select_option("#twStopSelect", "1")
    page.fill("#twEarliestInput", "10")
    page.fill("#twLatestInput", "40")
    page.click("#twAddBtn")

    badge_count = page.evaluate("document.querySelectorAll('.pin-tw-badge').length")
    badge_tip = page.eval_on_selector(".pin-tw-badge", "el => el.title")

    # Removing the rule takes the badge away again.
    page.click("#timeWindowsList button")
    badge_count_after_remove = page.evaluate("document.querySelectorAll('.pin-tw-badge').length")

    page.close()
    assert badge_count == 1
    assert "10" in badge_tip and "40" in badge_tip
    assert badge_count_after_remove == 0


# ---------- Quantum vs. Classical Arena (Wow #1) ----------
# compareMethods()'s "3, 2, 1, GO" countdown + simultaneous-draw race +
# winner banner sequence only runs for a real visitor (gated behind
# `!navigator.webdriver`, same technique the first-run tour uses) — so
# these spoof navigator.webdriver back to `false` to exercise it, and
# stub BOTH /api/solve responses directly (rather than relying on
# whatever the real solver happens to return for a synthetic matrix) so
# the "winner" is deterministic and the two draw-in durations are
# reliably different.

def _stub_solve_costs(page, quantum_cost, classical_cost):
    """Fulfils /api/solve with a minimal-but-complete response shaped like
    the real one (see app.py's /api/solve and tests/test_app.py), with a
    fixed cost_minutes per method so the Arena's winner/margin is known in
    advance instead of depending on whatever the real solver finds for a
    made-up distance matrix."""
    def handle(route, request):
        import json as _json
        body = _json.loads(request.post_data)
        cost = quantum_cost if body["method"] == "quantum" else classical_cost
        n = len(body["matrix"])
        route.fulfill(json={
            "order": list(range(n)),
            "cost_minutes": cost,
            "free_flow_minutes": cost * 0.7,
            "naive_order_minutes": cost * 1.2,
            "savings_vs_naive_pct": 15.0,
            "solve_ms": 5,
            "hour_simulated": 12.0,
        })
    page.route("**/api/solve", handle)


def test_arena_shows_a_countdown_then_a_winner_banner_for_a_real_visitor(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
    _stub_map_tiles(page)
    _stub_osrm(page, 4)
    _stub_solve_costs(page, quantum_cost=20.0, classical_cost=24.6)  # quantum wins by 4.6 min
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62); }
    """)
    page.click("#optionsBtn")
    page.click("#compareBtn")

    # The countdown is real (the whole point), so catch it appearing at all.
    page.wait_for_selector(".arena-countdown", timeout=3000)

    # Then the live "Racing…" state with its ticking timer.
    page.wait_for_selector(".arena-racing #arenaTimer", timeout=3000)

    # And finally the winner banner, naming the actual margin.
    page.wait_for_selector(".arena-banner", timeout=8000)
    banner_text = page.inner_text(".arena-banner")
    layer_count = page.evaluate("compareRouteLayer.getLayers().length")

    page.close()
    assert "Quantum-inspired won by 4.6 min" in banner_text
    assert layer_count == 2


def test_arena_shows_a_dead_heat_banner_when_costs_tie(live_server, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
    _stub_map_tiles(page)
    _stub_osrm(page, 4)
    _stub_solve_costs(page, quantum_cost=22.0, classical_cost=22.0)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62); }
    """)
    page.click("#optionsBtn")
    page.click("#compareBtn")

    page.wait_for_selector(".arena-banner", timeout=8000)
    banner_text = page.inner_text(".arena-banner")
    is_tie_styled = "tie" in (page.get_attribute(".arena-banner", "class") or "")

    page.close()
    assert "Dead heat" in banner_text
    assert is_tie_styled


def test_arena_sequence_is_skipped_under_automation_by_default(live_server, browser):
    """Without the navigator.webdriver spoof, Playwright's own default
    (navigator.webdriver === true) should make compareMethods() skip
    straight past the countdown/race delay to the results — this is what
    keeps every OTHER Compare-panel test in this file fast, so it's worth
    asserting directly rather than only relying on their timeouts passing."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    _stub_osrm(page, 3)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.evaluate("() => { addPoint(12.97, 77.59); addPoint(12.93, 77.62); addPoint(12.91, 77.63); }")

    page.click("#optionsBtn")
    page.click("#compareBtn")
    page.wait_for_function(
        "document.getElementById('compareContent').textContent.includes('Drive time')", timeout=2000,
    )
    countdown_ever_shown = page.evaluate("!!document.querySelector('.arena-countdown')")

    page.close()
    assert countdown_ever_shown is False


# ---------- Mobile pass (Week 4): slim topbar + drawer at 375px ----------
# Two real bugs found while verifying the topbar/drawer one-handed at phone
# width, both fixed alongside these tests:
#  1. Every floating panel the Options drawer can launch (Precedence, Time
#     windows, Import, My routes, Compare) rendered UNDER the drawer at its
#     own <=480px "full width" breakpoint (#optionsDrawer's z-index sits
#     above them) — invisible, not literally broken, but unreachable
#     one-handed. Fixed by closing the drawer when any of those open at
#     narrow width (_closeOptionsDrawerIfNarrow).
#  2. Every centered floating panel's entrance animation (.panel-enter /
#     @keyframes panelIn) used to animate `transform: translateY(...)`,
#     the SAME CSS property the panel's own `left: 50%; transform:
#     translateX(-50%)` centering rule uses — for the ~320ms animation,
#     that replaced the centering entirely, so the panel rendered flush
#     against its left edge (overflowing off-screen on a narrow phone)
#     until the animation finished. Fixed by animating `margin-top`
#     instead, which can never collide with any element's own transform.

@pytest.mark.parametrize("panel_id,open_sequence", [
    ("precedencePanel", ["#optionsBtn", "#precedenceBtn"]),
    ("timeWindowsPanel", ["#optionsBtn", "#timeWindowsBtn"]),
    ("importPanel", ["#optionsBtn", "#importBtn"]),
    ("historyPanel", ["#optionsBtn", "#historyBtn"]),
    ("comparePanel", ["#optionsBtn", "#compareBtn"]),
])
def test_options_drawer_closes_for_its_own_panels_at_phone_width(live_server, browser, panel_id, open_sequence):
    page = browser.new_page(viewport={"width": 375, "height": 812})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    # 4 points -> 2 interior stops, enough for every panel's form (Compare
    # just needs >= 2 points; Precedence needs 2 interior stops to offer a
    # real u/v pair).
    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62); }
    """)

    for selector in open_sequence:
        page.click(selector)
    page.wait_for_function(f"getComputedStyle(document.getElementById('{panel_id}')).display === 'flex'", timeout=3000)

    drawer_display = page.eval_on_selector("#optionsDrawer", "el => getComputedStyle(el).display")
    panel_rect = page.evaluate(f"""
        () => {{ const r = document.getElementById('{panel_id}').getBoundingClientRect(); return {{left: r.left, right: r.right}}; }}
    """)

    page.close()
    assert drawer_display == "none"
    assert panel_rect["left"] >= 0
    assert panel_rect["right"] <= 375


def test_options_drawer_stays_open_for_its_own_panels_at_desktop_width(live_server, browser):
    """The narrow-width fix must NOT change desktop behavior — the drawer
    is a narrow right-side panel there, not a full-width overlay, so it
    can and should stay open alongside a centered floating panel (a real
    user might want to keep tweaking Method/Fleet/Hour while a panel is
    open)."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.evaluate("() => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62); }")

    page.click("#optionsBtn")
    page.click("#precedenceBtn")
    page.wait_for_function("getComputedStyle(document.getElementById('precedencePanel')).display === 'flex'", timeout=3000)
    drawer_display = page.eval_on_selector("#optionsDrawer", "el => getComputedStyle(el).display")

    page.close()
    assert drawer_display == "flex"


def test_options_drawer_no_longer_overlaps_the_right_corner_panels(live_server, browser):
    """Regression test for a live-demo screenshot: the always-visible
    stats-strip pill (top-right) sat half-cut under the Options drawer's
    left edge once the drawer opened, because both anchor to the same
    right edge and the drawer's z-index is higher. The fix shifts
    #statsStripBtn/#directions/#liveFeed left of the drawer instead of
    closing or hiding any of them (closing was tried and rejected: the
    Live re-optimize panel's own Stop button lives INSIDE the drawer, so
    it must stay open and reachable while that panel runs) — checked here
    both ways: the stats pill's bounding box must never intersect the
    open drawer's, and it must go back to its original position once the
    drawer closes."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    closed_box = page.eval_on_selector(
        "#statsStripBtn", "el => { const r = el.getBoundingClientRect(); return {left: r.left, right: r.right}; }"
    )

    page.click("#optionsBtn")
    page.wait_for_function("getComputedStyle(document.getElementById('optionsDrawer')).display === 'flex'", timeout=3000)
    # the CSS transition on `right` needs a moment to settle before reading boxes
    page.wait_for_timeout(300)

    stats_box = page.eval_on_selector(
        "#statsStripBtn", "el => { const r = el.getBoundingClientRect(); return {left: r.left, right: r.right}; }"
    )
    drawer_box = page.eval_on_selector(
        "#optionsDrawer", "el => { const r = el.getBoundingClientRect(); return {left: r.left, right: r.right}; }"
    )

    page.click("#optionsClose")
    page.wait_for_function("getComputedStyle(document.getElementById('optionsDrawer')).display === 'none'", timeout=3000)
    page.wait_for_timeout(300)
    reopened_box = page.eval_on_selector(
        "#statsStripBtn", "el => { const r = el.getBoundingClientRect(); return {left: r.left, right: r.right}; }"
    )

    page.close()

    assert stats_box["right"] <= drawer_box["left"], "stats pill must not overlap the open drawer"
    assert stats_box["left"] < closed_box["left"], "the pill should have shifted left while the drawer was open"
    assert reopened_box == closed_box, "closing the drawer must restore the pill's original position exactly"


# ---------- SIH Round-2 judge-review follow-ups ----------
# A second, independent review (SIH-Round2-Judge-Review.docx) verified live,
# in a network-restricted sandbox, that a plain fetch() failure (OSRM/
# Nominatim unreachable — exactly what a filtered or congested venue wifi
# would produce) surfaced as a raw browser TypeError ("Failed to fetch")
# in the error toast, reading as the app being broken rather than the
# network. The two tests below lock in the fix: _friendlyErrorMessage()
# translates that one specific failure signature, and _checkNetworkHealth()
# proactively surfaces it as a banner pointing at the zero-dependency
# /demo page, rather than waiting for a judge to hit Solve and find out.

def test_raw_fetch_failures_get_a_friendly_message_not_the_browser_error(live_server, browser):
    """_friendlyErrorMessage() must recognize the browser's own generic
    network-failure wording and replace it — but leave a REAL, specific
    error (our own API's 400, an OSRM "no route" message) completely
    alone, since that's actionable information a user should still see."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    friendly = page.evaluate("""
        () => _friendlyErrorMessage(new TypeError('Failed to fetch'))
    """)
    friendly_safari = page.evaluate("""
        () => _friendlyErrorMessage(new TypeError('Load failed'))
    """)
    real_error = page.evaluate("""
        () => _friendlyErrorMessage(new Error('Could not find a driving route between those points.'))
    """)
    fallback = page.evaluate("""
        () => _friendlyErrorMessage(new Error(''), 'Incident simulation failed.')
    """)

    page.close()

    assert 'failed to fetch' not in friendly.lower()
    assert '/demo' in friendly
    assert 'failed to fetch' not in friendly_safari.lower() and '/demo' in friendly_safari
    assert real_error == 'Could not find a driving route between those points.'
    assert fallback == 'Incident simulation failed.'


def test_network_health_banner_shows_only_when_osrm_is_unreachable(live_server, browser):
    """Two runs of the same real function, _checkNetworkHealth(): once
    with OSRM stubbed to fail (banner must appear, linking to /demo),
    once with it stubbed to succeed (banner must stay hidden) — proving
    the check is a real reachability probe, not decoration that always
    shows or never shows."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.route("**router.project-osrm.org/table/**", lambda route: route.abort())
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.evaluate("() => _checkNetworkHealth()")
    page.wait_for_function("document.getElementById('networkBanner').style.display === 'flex'", timeout=6000)
    banner_html = page.inner_html("#networkBanner")
    assert '/demo' in banner_html
    page.click("#networkBannerClose")
    assert page.eval_on_selector("#networkBanner", "el => el.style.display") == "none"
    page.close()

    page2 = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page2)
    page2.route("**router.project-osrm.org/table/**", lambda route: route.fulfill(
        json={"code": "Ok", "durations": [[0, 300], [300, 0]]}
    ))
    page2.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page2.evaluate("() => _checkNetworkHealth()")
    page2.wait_for_timeout(500)
    still_hidden = page2.eval_on_selector("#networkBanner", "el => getComputedStyle(el).display")
    page2.close()
    assert still_hidden == "none"


def test_ps_alignment_badge_is_visible_at_desktop_width_and_hidden_at_phone_width(live_server, browser):
    """Feature 02 from the judge review: nothing previously told a judge,
    on screen, how the live app maps to PS SIH26137's actual objectives —
    it lived only in the README. The badge is deliberately hidden below
    860px (same breakpoint the brand's own <h1> already hides at) rather
    than fight for space in an already-tight phone topbar."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    desktop_visible = page.is_visible(".ps-badge")
    tooltip_text = page.get_attribute(".ps-badge + .info-icon", "title") or page.evaluate(
        "() => document.querySelector('.ps-badge + .info-icon').dataset.tip"
    )
    page.close()

    page2 = browser.new_page(viewport={"width": 500, "height": 900})
    _stub_map_tiles(page2)
    page2.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    phone_hidden = page2.is_hidden(".ps-badge")
    page2.close()

    assert desktop_visible
    assert phone_hidden
    assert "SIH26137" in tooltip_text and "convergence speed" in tooltip_text.lower()


@pytest.mark.parametrize("panel_id,open_sequence", [
    ("precedencePanel", ["#optionsBtn", "#precedenceBtn"]),
    ("timeWindowsPanel", ["#optionsBtn", "#timeWindowsBtn"]),
    ("importPanel", ["#optionsBtn", "#importBtn"]),
    ("historyPanel", ["#optionsBtn", "#historyBtn"]),
])
def test_centered_panels_stay_within_viewport_during_their_entrance_animation(live_server, browser, panel_id, open_sequence):
    """Regression test for the transform-collision bug above: check the
    panel's actual bounding box WHILE its 0.32s entrance animation is
    still running (not after it settles), since that's exactly when the
    bug showed up — the panel was fine before and after the animation,
    only wrong during it."""
    page = browser.new_page(viewport={"width": 375, "height": 812})
    _stub_map_tiles(page)
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)
    page.evaluate("""
        () => { addPoint(12.97, 77.59); addPoint(12.95, 77.60); addPoint(12.93, 77.61); addPoint(12.91, 77.62); }
    """)

    for selector in open_sequence:
        page.click(selector)
    page.wait_for_function(f"getComputedStyle(document.getElementById('{panel_id}')).display === 'flex'", timeout=3000)
    page.wait_for_timeout(60)  # well inside the 320ms animation — the worst moment for the old bug
    rect = page.evaluate(f"""
        () => {{ const r = document.getElementById('{panel_id}').getBoundingClientRect(); return {{left: r.left, right: r.right}}; }}
    """)

    page.close()
    assert rect["left"] >= 0
    assert rect["right"] <= 375


def test_insights_dashboard_is_reachable_from_the_drawer_below_860px(live_server, browser):
    """statsStripBtn (the always-visible pill that normally opens the
    Insights dashboard) hides below 860px width to keep the topbar from
    overflowing — which used to leave the dashboard completely
    unreachable on anything narrower than that. drawerInsightsBtn is the
    fallback entry point inside the Options drawer."""
    page = browser.new_page(viewport={"width": 375, "height": 812})
    page.goto(f"{live_server}/app", wait_until="networkidle", timeout=15000)

    stats_strip_hidden = page.eval_on_selector("#statsStripBtn", "el => getComputedStyle(el).display") == "none"

    page.click("#optionsBtn")
    page.click("#drawerInsightsBtn")
    page.wait_for_function("getComputedStyle(document.getElementById('insightsPanel')).display === 'flex'", timeout=3000)
    drawer_display = page.eval_on_selector("#optionsDrawer", "el => getComputedStyle(el).display")
    panel_rect = page.evaluate(
        "() => { const r = document.getElementById('insightsPanel').getBoundingClientRect(); return {left: r.left, right: r.right}; }"
    )

    page.close()
    assert stats_strip_hidden  # confirms this test is actually exercising the narrow-width gap
    assert drawer_display == "none"
    assert panel_rect["left"] >= 0
    assert panel_rect["right"] <= 375
