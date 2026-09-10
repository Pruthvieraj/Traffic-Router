# The Live App (`app.py`) and the UI

[← Back to README](../README.md)

## `app.py` — click anywhere in the city (real streets, real solve, live)

Run `python3 app.py`, open `http://127.0.0.1:5000`. Click the map — type a
place name into the search box and pick it from the live autocomplete
suggestions — or tap the microphone icon inside the search box and just
say the place name (built on the browser's own Web Speech API, no extra
service or API key; the mic only appears in browsers that support it, so
typing always works as the fallback everywhere) — to drop a **Start** pin
(green "S"), then an **End** pin (red "E"), then optionally more stops in
between (up to `MAX_STOPS` total, 40 by default — see "Scaling past a
dozen stops" below for how it stays fast at that size). Hit **Solve
route** and it:

1. Gets a real, road-network-based travel-time matrix between all your
   points from OSRM (a public routing engine), not a straight-line
   estimate.
2. Solves the best visiting order with a **fixed start and fixed end**
   (a proper A-to-B route through your stops, not a round trip back to
   start) — this is a different, harder-to-get-right QUBO formulation than
   the round-trip one everything else in this project uses (see
   `qubo_tsp.build_open_path_bqm`'s docstring for exactly how the fixed
   endpoints are guaranteed correct by construction, not just penalized).
   Verified against brute-force-optimal on 20 random test cases before
   shipping — see the project's build history if you want to rerun that check.
3. Draws the actual street-following route geometry for that order (again
   via OSRM), so it curves along real roads instead of drawing straight
   lines between points.

**Architecture note — why this changed from an earlier version.** The
first version of this feature fetched OpenStreetMap street data on the
*server* (via a Python library called osmnx, talking to OpenStreetMap's
Overpass API). That works on a laptop but is unreliable once deployed to
a cloud host: Overpass's operators rate-limit or block traffic from
datacenter IP ranges to protect the service from bots, so the exact same
code would silently fall back to a tiny curated dozen-landmark network on
Render, producing straight-line "routes" and "nearest known road junction"
snap warnings. The fix was to move all real road-network queries into the
**browser** using OSRM (`router.project-osrm.org`) — the browser reaches
it from the visitor's own ordinary internet connection, not a flagged
datacenter IP, which is exactly how real map apps handle this. `app.py`'s
`/api/solve` endpoint now does pure optimization on a matrix the browser
already computed — no maps, no Overpass, nothing left to fail on a cloud
host. (`prefetch_street_graphs.py` and the osmnx-based code in
`src/city_graph.py` are left in the project for reference but are no
longer used by `app.py`.)

**The one remaining caveat:** this needs live internet for the map tile
images (same as `multi_city_map.html`) and for the browser's calls to
OSRM and to OpenStreetMap's search service. `router.project-osrm.org` is
a free public demo instance — reliable for occasional/demo-scale use like
a hackathon, but not a guaranteed-uptime production service, so if it's
ever briefly unreachable the app will show a clear error (e.g. "Routing
service returned 500") rather than pretending to succeed.

**Why this needs a running server at all** (unlike the double-click-a-file
simplicity of `multi_city_map.html`): the visiting-order optimization
(QUBO + simulated annealing, or the classical baseline) is real Python
computation that has to run somewhere in response to each solve — a
static HTML file can't do that on its own, even though the mapping parts
now live entirely in the browser.

**Traffic-awareness — why it used to show flat free-flow numbers, and the
fix.** OSRM's Table/Route APIs report *free-flow* travel time only — the
time it'd take with zero congestion, at any hour, any day. That's why an
early version of this app could show something like "24 km, 24 minutes"
for a route that would obviously take longer at 6:30pm — there was no
traffic model in the loop at all, it was pure shortest-path.

`/api/solve` now runs the browser's real, OSRM-derived travel-time matrix
through `src/congestion.py`'s `apply_congestion_to_matrix()` *before*
optimizing, and solves on the congested matrix — so the chosen route
itself, not just the displayed number, changes when traffic is heavier
enough to make a different stop order faster. The UI's time-of-day
dropdown ("Morning peak", "Evening peak", "Late night", etc.) picks the
`hour` sent with the solve request, and the stats panel shows both:

- **Estimated drive time (with traffic)** — `cost_minutes`, on the
  congested matrix, for the solved order.
- **Free-flow (no-traffic) baseline** — `free_flow_minutes`, the same
  solved order's time with the congestion model switched off, so you can
  see exactly how much of the estimate is "traffic" versus "distance."
- **% faster than naive order** — `savings_vs_naive_pct`, comparing the
  solved order's congested cost against simply visiting the stops in the
  order they were clicked, *under the same simulated traffic* — this is
  the number that answers "so what did the optimizer actually save?"

**Said plainly, because judges will ask:** the DEFAULT congestion layer
(`rush_hour_multiplier()` — two Gaussian bumps around 9am and 6:30pm, plus
small seeded per-pair variation so not every road is hit identically) is a
**simulated time-of-day model, not a live traffic sensor feed** — the app
says this directly in its own UI, right next to the numbers, and it's what
every live demo of this app uses unless `TRAFFIC_PROVIDER` is changed. The
road *geometry* and *distances* are real (from OSRM); the *congestion* on
top of them is, by default, a disclosed, reproducible simulation, the same
honest framing this project has used everywhere else (see "The honest
finding" below).

**The upgrade path to real live traffic is no longer just a paragraph — it's
a real, working integration you can turn on with your own API key.**
`src/traffic_provider.py` defines `TrafficProvider` — anything with a
`get_congested_matrix(W_free_flow, hour, coords=None)` method — and `app.py`
picks one by name via the `TRAFFIC_PROVIDER` environment variable (default
`simulated`), never calling `congestion.py` directly:

- `simulated` (default) — `SimulatedTrafficProvider`, the reproducible model
  above. Needs no API key, no network access, no coordinates.
- `google_routes` — `GoogleRoutesTrafficProvider`, a REAL integration with
  Google's Routes API "Compute Route Matrix" endpoint
  (`routingPreference=TRAFFIC_AWARE_OPTIMAL`). Set `TRAFFIC_PROVIDER=google_routes`
  and a `GOOGLE_ROUTES_API_KEY` (your own Google Cloud API key with the
  Routes API enabled and billing configured — see
  [Google's setup docs](https://developers.google.com/maps/documentation/routes/compute_route_matrix))
  and `/api/solve` / `/api/solve_fleet` will fetch genuinely live,
  traffic-aware travel times for the exact waypoints being solved, instead
  of simulating them. This sandbox has no such key configured, so it can't
  be demonstrated end-to-end here — the same honest limitation as the real
  QPU integration (see below): the wiring is real and tested, the live call
  isn't something this environment can make.
- `live` — `LiveTrafficProviderStub`, a placeholder for any OTHER paid
  provider (TomTom, HERE, Mapbox) that isn't `google_routes`, raising a
  clear `NotImplementedError` if selected rather than silently pretending
  to have live data it doesn't.

**A real wrinkle this surfaced, and how it's handled.** A live traffic API
computes travel times FROM real coordinates — it can't retrofit live
traffic onto an already-computed free-flow matrix the way the simulated
multiplier model does, and this project's optimization core (the QUBO
solver, distance_matrix.py) never needed coordinates before, only a travel-
time matrix. So `get_congested_matrix` gained an optional third parameter,
`coords`, that `SimulatedTrafficProvider` ignores and `GoogleRoutesTrafficProvider`
requires (raising a clear error if it's missing rather than guessing).
`app.py`'s `/api/solve` and `/api/solve_fleet` both accept an optional
`points` request field (`[[lat, lon], ...]`, matching the matrix's rows)
threading exactly this through — `templates/click_router.html` already
sends it (the browser has the clicked points' real coordinates anyway), so
switching `TRAFFIC_PROVIDER` to `google_routes` with a real key works
end-to-end through the live app with no frontend changes needed.

**Testability without a real key or network access** follows the same
dependency-injection pattern as the real QPU integration
(`qpu_solver.py`'s `sampler=` override): `GoogleRoutesTrafficProvider`
accepts an optional `session` object exposing the same
`.post(url, headers=, json=, timeout=) -> response` shape `requests` does,
so `tests/test_traffic_provider.py` verifies request construction and
response parsing (including a genuinely asymmetric real-world matrix — one-
way streets make A→B and B→A different, unlike the simulated provider's
symmetric multiplier) with a lightweight fake session, no credentials
needed. This sandbox's own real, unmocked lack of `GOOGLE_ROUTES_API_KEY`
is used to test the real "no key configured" failure path, the same way
the QPU tests use this sandbox's real lack of a D-Wave token.

Swapping in a *different* real provider (TomTom/HERE/Mapbox) is still
"write one new class in this file, change one env var" — provably, since
`app.py` never imports `congestion.py` at all anymore.

For a real deployment, `OSRM_BASE_URL` (an environment variable, defaults
to the free public `router.project-osrm.org` demo server) lets you point
at a self-hosted OSRM instance instead, without touching code — worth
doing if you outgrow the demo server's fair-use limits.

**Dynamic re-optimization — simulating an incident.** A static "best order,
computed once" route is only half of what judges mean by "traffic-aware
routing" — the other half is reacting when something changes mid-route.
Every stop-arrival line in the turn-by-turn directions panel has a
"⚠ Simulate incident here" button: clicking it re-solves the exact same
stops with a 4× congestion spike applied to that one leg
(`src/congestion.py`'s `apply_incident_spikes`, via `/api/solve`'s optional
`incident_pairs` field) and redraws whatever new order the optimizer finds
— genuinely re-routing around the "closure" when an alternative exists,
not just re-labeling the same path. `tests/test_app.py`'s
`test_solve_incident_pairs_can_change_the_chosen_order` proves this isn't
cosmetic: it asserts the chosen order actually differs once the spike is
applied.

**Continuous re-optimization — the "Live re-optimize" demo.** The incident
button above is one manual re-solve, triggered by a click. Once a route is
solved (single-vehicle OR fleet mode — see below), the "▶ Live
re-optimize" button in the topbar automates a repeated version of the same
thing: every 4 seconds, a simulated clock advances 15 minutes, a random
leg has roughly a 1-in-3 chance of getting the same incident spike
`simulateIncident()` uses, and the exact same solve endpoint is called
again — no separate, unverified code path, just the ordinary solve loop
run on a timer. A live feed panel logs each tick ("6:45 PM — traffic
shifted, rerouted (38.2 min, -3.1 min)" / "7:00 PM — checked, current order
still best (41.0 min, +0.0 min)"), and the map redraws only when the
optimizer actually finds a different order, so the "rerouted" moments are
genuinely earned, not cosmetic. It auto-stops after 20 cycles (a demo
safety cap, and comfortably under `/api/solve`'s 20-requests/minute rate
limit) or immediately if a manual solve, a vehicle-count/mode switch, or
clearing points supersedes it.

**Said plainly, because judges will ask:** this is a simulated clock
ticking forward through `src/congestion.py`'s time-of-day model, not a
live GPS feed or a real fleet's position updating in real time — the same
honest framing this project uses everywhere else. The tick-by-tick
decision logic (advancing the simulated hour, picking whether/where to
inject an incident, and phrasing what the feed says happened) lives in
`static/route_helpers.js` as plain, dependency-free functions — the same
file the turn-by-turn directions formatting already lived in — and is unit
tested in `tests/frontend/route_helpers.test.js` with fixed random-number
inputs, so the decision logic is verified without needing a running
browser or a timer.

**Fleet mode is now covered too.** `liveReoptTick()` dispatches to either
`_liveReoptTickSingle()` (the original loop, unchanged) or
`_liveReoptTickFleet()` depending on which mode the last real solve was
in. The fleet tick re-solves against `/api/solve_fleet` using the exact
fleet configuration (vehicle count, capacity cap, demand weights) from
that last solve, applies the same simulated-clock/random-incident logic,
and redraws every vehicle's own route in its own color (with its own
traveling-marker animation) whenever any vehicle's own stop order changes
— `fleetOrderChanged()` in `static/route_helpers.js` (unit tested
alongside the rest of that file) decides that by comparing each vehicle's
order tick-to-tick, not just the fleet total. This needed `/api/solve_fleet`
to accept `incident_pairs`/`incident_multiplier` too (previously
`/api/solve`-only) — see app.py's `solve_fleet()` and
`tests/test_app.py`'s `test_solve_fleet_with_incident_pairs_*` tests. What's
still NOT done: precedence rules aren't sent to `/api/solve_fleet` even on
a manual fleet solve (see "Precedence" above), so the live loop doesn't
invent that either — it only re-solves whatever a manual fleet solve
already sends. Tested at three levels: `fleetOrderChanged()`'s own
decision logic is unit tested (`tests/frontend/route_helpers.test.js`),
`/api/solve_fleet`'s new `incident_pairs` support is tested via the Flask
test client (`tests/test_app.py`), and the actual end-to-end dispatch
(`liveReoptTick()` picking the fleet tick over the single-vehicle one,
solving, and logging a real tick) is covered by a real-browser Playwright
test (`test_live_reopt_works_in_fleet_mode_and_ticks_without_crashing` in
`tests/test_layout.py`) the same way the single-vehicle loop already was.

**Multi-vehicle dispatch — a first step toward real VRP.** Everything
above is single-vehicle TSP: one start, one end, one route. The "Vehicles"
selector in the topbar is the honest next step: pick 2 or 3 vehicles and
your first clicked point becomes a shared depot, with the remaining stops
split across vehicles (deterministic farthest-point clustering — the same
method `src/clustering.py` already used for single-vehicle scaling) and
each vehicle's own depot-to-stops-and-back tour solved exactly with the
same QUBO/classical solver used everywhere else in this project (see
`solve_multi_vehicle` in `src/clustering.py`, served by the separate
`/api/solve_fleet` endpoint so the single-vehicle contract above is
completely unchanged).

**The split is balanced by default, not just proximity-based.**
Farthest-point clustering alone has no notion of fairness — it seeds
clusters by distance and assigns every other stop to whichever seed is
nearest, which in practice can hand one vehicle a wildly disproportionate
share purely because of how stops happen to be distributed in space (a
real run: 16 stops across 2 vehicles came out 14-and-2). Every solve now
rebalances the clusters afterward against a size target — by default a
fair-share target of `ceil(stops / n_vehicles)` (the size an exactly even
split would produce), so a default multi-vehicle solve is balanced with no
extra input needed. `tests/test_clustering.py`'s
`test_default_split_is_balanced_even_with_no_explicit_capacity` reproduces
that exact 14-vs-2 distribution shape and confirms it now splits evenly.

On top of that default balancing, it also supports a **real, enforced,
stricter capacity constraint.** Selecting multi-vehicle mode reveals a
"Max/vehicle" field — set it below the fair share and no single vehicle
will be handed more stops than that cap, full stop
(`_rebalance_for_capacity` in `src/clustering.py` greedily moves points
off an overloaded cluster onto the nearest under-capacity one's medoid
until every cluster satisfies the cap). If the requested vehicle count
can't possibly satisfy the cap you asked for (e.g. 10 stops, cap of 3,
only 1 vehicle requested), the vehicle count is automatically raised until
it can (`ceil(stops / capacity)`) rather than silently violating the limit
or dropping stops — the stats panel says so explicitly when this happens.
`tests/test_clustering.py`'s capacity tests assert this directly (every
vehicle's stop count `<= cap`, every stop still assigned exactly once, and
`n_vehicles` genuinely rising when the requested fleet is too small), and
it's wired end-to-end through `/api/solve_fleet`'s `max_stops_per_vehicle`
field. **Said plainly:** this is still not a full capacitated VRP solver —
no time windows, no simultaneous joint optimization across vehicles. What
it proves is that the underlying solver and architecture generalize past a
single vehicle *with* a real constraint enforced on top, which is the real
gap between a TSP demo and a fleet dispatch system, without dressing this
up as more than it is.

**Per-stop demand weights — capacity by load, not just stop count.** The
cap above only means something if every stop is equally "heavy." Real
deliveries aren't — a crate of vegetables and a pallet of cement don't take
the same truck space. The "Capacity mode" dropdown next to "Max/vehicle"
switches that field's meaning from a stop *count* to a total *weight*
limit, and a "Weights" button opens a panel listing every current stop
with an editable weight (default 1). The same `matrix`/`n_vehicles`
request now carries `demands` (a `{stop_index: weight}` map) and
`vehicle_capacity`, and `solve_multi_vehicle` in `src/clustering.py`
enforces the cap on total demand per vehicle, not stop count
(`_cluster_size` sums weights instead of counting stops when demands are
given). **A real bin-packing subtlety, caught by the test suite rather
than shipped broken:** `ceil(total_demand / vehicle_capacity)` is only a
*lower bound* on the vehicles needed — with uneven weights (say nine
40kg stops and one 90kg stop, capacity 100), the naive ceiling
undercounts, because clustering-then-rebalancing can still leave a
cluster over the line even when the arithmetic total fits. The fix is a
retry loop: after clustering and rebalancing, if any vehicle still
exceeds capacity, `n_vehicles` is incremented and the split redone, up to
the guaranteed-feasible worst case of one stop per vehicle (every stop's
own weight is validated against the capacity up front, so that terminal
state always exists). `tests/test_clustering.py`'s
`test_demand_capacity_is_actually_enforced_on_every_vehicle` and
`test_demand_capacity_auto_raises_vehicle_count_when_too_small` are the
tests that caught this before it shipped. Mutually exclusive with
`max_stops_per_vehicle` (a vehicle has one capacity, not two competing
definitions of it); `demands`/`vehicle_capacity` are optional, and a stop
missing from `demands` defaults to weight 1.

**Basic API hardening.** `/api/solve` and `/api/solve_fleet` are both
rate-limited to 20 requests/minute per IP (via `flask-limiter`) so a public
demo URL can't be trivially hammered. This is automatically disabled while
running the pytest suite (which legitimately calls these endpoints far
more than 20 times a minute) and degrades gracefully — no rate limiting,
not a crash — if `flask-limiter` somehow isn't installed.

**A basic analytics endpoint — a live number instead of a claim.**
`GET /api/analytics` (no auth needed — there's nothing sensitive in an
aggregate count) returns how many solves this running process has served,
split by endpoint (`/api/solve` vs `/api/solve_fleet`) and by method
(quantum vs classical), how many failed, the average solve time, and how
often the incident/precedence/demand-weight features actually got
exercised — see `src/analytics.py`. It's now backed by a local SQLite
file (`instance/analytics.db`, path overridable via `ANALYTICS_DB_PATH`),
written through on every recorded solve/error, so the counts survive a
plain process restart (including Render free-tier's spin-down/spin-up
cycle) and stay complete across multiple worker processes sharing that
same file on one machine. **Said plainly, because this is still the kind
of thing that's easy to oversell:** it is NOT durable across a fresh
deploy — Render's free tier provisions a new disk on redeploy, so the
counts reset then regardless — and it does NOT share counts across
multiple separate machines (horizontal scaling); either of those would
need real shared infrastructure (a managed Postgres/Redis instance), which
this demo doesn't carry just to show a request count. This project's
actual `Procfile` still runs a single gunicorn worker, so today's real
deployment was never affected by the per-worker-fragmentation limit this
change also happens to fix. It stores no per-request data whatsoever — no
IPs, no matrices, no per-call timestamps, only aggregate counts, in memory
and in the SQLite file alike — which is also exactly why it needs no auth.
`tests/test_app.py`'s analytics tests assert the counters actually
increment correctly per endpoint/method/flag and that the response never
grows extra fields beyond the documented aggregate set.

## The interface — what changed and why

`templates/click_router.html` was reworked from a functional-but-plain
utility page into something closer to a real product, on the theory that a
judge's first ten seconds are visual before they're technical:

- **A real design system** instead of default browser styling: a dark
  gradient topbar, a consistent indigo/violet/cyan accent palette used for
  every button, pin, and the route line itself, custom-skinned dropdowns
  (the browser's default `<select>` look is gone), Google's Inter typeface,
  and frosted-glass ("backdrop-blur") cards for the hint, stats, directions,
  and error panels instead of flat white boxes.
- **Visible loading states.** Solving used to give zero feedback until it
  either finished or errored — now the Solve button shows a spinner and
  walks through what's actually happening ("Computing travel times…" →
  "Optimizing route…" → "Drawing route…"), so a slow OSRM response reads as
  "working" instead of "frozen."
- **The route draws itself in**, animating along the real street geometry
  over about a second, followed by a small marker that travels the full
  route — a deliberate "the optimizer just computed this" moment rather
  than a polyline appearing instantly.
- **A visible naive-vs-optimized comparison.** When the optimized order
  differs meaningfully from the as-clicked order, the app now also fetches
  and draws the naive route as a faded dashed line underneath the solid
  optimized one, with a small legend — so the `savings_vs_naive_pct` number
  in the stats panel is something you can actually *see* on the map, not
  just a claim in text.
- **Editable pins.** Stop markers are now draggable (drag to reposition,
  then re-solve) and clickable-to-remove (no more all-or-nothing "Clear
  points" for a single misplaced stop), each with a small drop-in animation
  when placed.
- **Mobile-usable layout.** Panels reflow to full-width and stack sensibly
  under ~860px width instead of overlapping.
- **Voice search.** A microphone icon inside the search box lets you speak
  a place name instead of typing it, using the browser's built-in Web
  Speech API — no external service, no API key. It feature-detects
  support and only shows itself where the browser actually has it,
  degrading invisibly (typed search keeps working everywhere) rather than
  showing a button that doesn't work.
- **Smarter search for real Indian addresses.** A specific housing society
  or apartment building (e.g. "Sukhwani Gracia C") often exists in
  OpenStreetMap under its base name but not with the exact wing/tower/phase
  suffix you'd naturally type — a single rigid query used to just fail
  silently on these. Search now retries with progressively broader
  phrasings (dropping the country suffix, then stripping a trailing
  wing/tower/phase/block-style token) before giving up, and softly biases
  results toward whichever city is selected. When every variant still comes
  back empty — which does happen; smaller/newer societies are genuinely not
  in OpenStreetMap's free database yet — the search box says so plainly and
  points at the one fallback that always works regardless of database
  coverage: switch to satellite view and click the exact building. See
  `tests/test_layout.py`'s two search-fallback tests for the exact scenario
  this fixes and how it's verified (with the real network call mocked out,
  so the test is deterministic).
- **Pan-India city coverage.** The city dropdown now spans 18 cities across
  every region of India instead of a handful clustered around Delhi NCR
  and Bengaluru — see [About `multi_city_map.html`](architecture.md) above for the full
  list and what this dropdown does (and doesn't) gate.
- **Fleet loads are now balanced by default.** A real live-demo bug: with
  no capacity limit set, plain farthest-point clustering could hand one
  vehicle a wildly disproportionate share of stops purely because of how
  they happened to be distributed in space — one run split 16 stops
  across 2 vehicles as 14-and-2. `solve_multi_vehicle` now always
  rebalances against a fair-share target of `ceil(stops / n_vehicles)`
  even when no explicit capacity is given, so a default multi-vehicle
  solve is balanced with no extra input required — the "Max/vehicle"
  field is now for a *stricter* cap than the fair share, not the only way
  to get a sane split. See `tests/test_clustering.py`'s
  `test_default_split_is_balanced_even_with_no_explicit_capacity`, which
  reproduces the exact 14-vs-2 distribution shape and asserts the fixed
  version splits it evenly.
- **Redesigned info-icon tooltips.** The small "i" icons next to the
  method/vehicle/capacity selectors used to rely on the browser's native
  `title=` tooltip — slow to appear, plain default styling, and completely
  unusable on touch devices (no hover state to trigger it). They're now a
  single shared, custom-styled floating bubble, positioned per-icon and
  kept fully on-screen regardless of window width, shown on hover *or*
  click/tap (so it works on phones), and dismissed on an outside click.
  See `tests/test_layout.py`'s two tooltip tests for the exact interaction
  behavior locked in (including a real bug this caught during development:
  a naive click-to-toggle implementation closed the tooltip instantly on
  desktop, because a mouse click always fires a hover event first).
- **Bulk import of stops.** An "Import stops" button opens a panel where
  you can paste many stops at once — one per line, either a direct
  `lat, lon` pair (added instantly, no network call) or a plain address
  (geocoded through the same Nominatim search + fallback logic described
  above, taking the top match since there's no dropdown to pick from for a
  bulk paste) — or upload a `.csv`/`.txt` file with the same one-per-line
  format instead of typing. Lines that can't be placed are reported by
  name rather than silently dropped, and the panel stays open until every
  line is either added or clearly explained. See
  `tests/test_layout.py`'s two bulk-import tests.
- **Shareable route link.** A "Share" button (enabled once you have 2+
  pins) copies a URL that encodes your pins plus the selected city,
  method, hour, and vehicle count — no account, no server-side storage,
  the state lives entirely in the link. Opening it reconstructs the same
  map and pins automatically; the recipient still clicks Solve route
  themselves (the link deliberately doesn't bake in an already-computed
  route, since OSRM's live travel-time estimates can shift between when a
  link is shared and when it's opened). See `tests/test_layout.py`'s two
  share-link tests (encode-then-decode round trip, and restoring straight
  from a URL).
- **GPX + printable itinerary export.** Once a single-vehicle route is
  solved, the stats panel gets two export buttons: "GPX" downloads a
  standard `.gpx` file (waypoints for each stop plus the real road-
  following track) that any GPS app, Google Maps, Garmin, or Strava can
  import — no library needed, it's plain XML built client-side. "Print /
  PDF" opens a clean, map-free numbered itinerary and calls the browser's
  own print dialog, whose "Save as PDF" option is the dependency-free path
  to a PDF for something this simple. Deliberately scoped to single-
  vehicle routes for this first cut, not fleet mode. See
  `tests/test_layout.py`'s two export tests.
- **Dark / light theme toggle — now a real day/night switch, not just an
  icon flip.** A sun/moon button switches every glass panel, dropdown, and
  text color between light and dark via CSS custom properties, **swaps the
  street-view map tiles** between CARTO Voyager (light) and CARTO Dark
  Matter (dark), and **recolors the topbar itself** (a soft light-lavender
  gradient with dark ink text in light mode, the original navy/indigo
  gradient with white text in dark mode) — the topbar used to be hardcoded
  dark in both themes, which, combined with #stats/#directions staying
  hidden until a route is solved, meant a real early report was right: the
  only thing that visibly changed on toggling used to be the sun/moon icon
  itself. Satellite view deliberately keeps one look in both themes (it's
  real aerial photography, not a cartographic style — there's nothing
  honest to "darken"), so only street view's tiles swap. Defaults to your
  OS-level dark-mode preference on a first visit, and remembers an explicit
  choice in `localStorage` after that, applied before first paint so
  there's no light-then-dark flash on reload. See `tests/test_layout.py`'s
  four theme tests, including `test_theme_toggle_also_swaps_the_street_basemap_tiles`
  and `test_theme_toggle_also_recolors_the_topbar_itself` (the latter also
  guards against a real bug caught while building this: a dark-mode
  dropdown-chevron override with just enough CSS specificity to defeat the
  ghost/danger buttons' own `background:` shorthand, which briefly
  resurrected a tiled chevron pattern across every ghost button in dark
  mode instead of their plain fill).
- **Precedence ("visit X before Y") rules.** A "Precedence" button opens a
  panel where you can require one stop to be visited before another — a
  pickup before its matching drop-off, say. This is a real constraint
  baked directly into the same QUBO/classical solve (extending
  `build_open_path_bqm` in `src/qubo_tsp.py` to accept `precedence`,
  mirroring the pattern `build_tsp_bqm` already used for the closed-loop
  case), not a filter applied to the result afterward. Honest scope: only
  supported up to the same interior-stop count a single QUBO can solve
  directly (`CLUSTER_SIZE`, 9 by default) — above that, stops get split
  across independently-solved clusters and a cross-cluster precedence pair
  can't be reliably enforced, so the API returns a clear 400 rather than
  silently ignoring it. Rules track the actual stops as the route gets
  (re-)solved (remapped through the solved order automatically) but are
  dropped if you add or remove a stop, since positions shift. See
  `tests/test_qubo_tsp.py`, `tests/test_clustering.py`, `tests/test_app.py`
  (including `test_solve_precedence_and_incident_compose_in_one_request`,
  which proves precedence and incident-triggered re-optimization actually
  work TOGETHER in one request, not just independently), and
  `tests/test_layout.py`'s precedence tests.

  `/api/solve_fleet` (multi-vehicle mode) now accepts the same
  `precedence` field too — `solve_multi_vehicle` in `src/clustering.py`
  enforces it on whichever vehicle a pair's two stops both land on, by
  solving that vehicle's leg with the depot pinned as both the fixed start
  *and* fixed end of the already-tested open-path solver, instead of the
  ordinary closed-loop one (a closed loop's position labeling is only
  unique up to rotation, which would otherwise make "before" ill-defined
  after the depot-first display rotation every vehicle's tour gets). Since
  which vehicle a stop lands on is decided by clustering *before*
  precedence is ever looked at, a pair split across two vehicles can't be
  enforced — the API returns a clear 400 naming both vehicles rather than
  silently dropping the rule. See `tests/test_clustering.py`'s
  precedence-in-fleet-mode tests and `tests/test_app.py`'s
  `test_solve_fleet_*precedence*` tests. The click-map UI's Precedence
  button still only appears in single-vehicle mode, on purpose: the UI
  can't know in advance which vehicle a stop will be clustered onto, so
  offering the rule builder in fleet mode would mean rules that
  unpredictably 400 depending on how the split happens to fall — an API
  consumer that already knows its own stop-to-vehicle assignment (or that
  pins `n_vehicles=1`) doesn't have that problem.
- **Method comparison — quantum-inspired vs. classical, side by side.** A
  "Compare methods" button (single-vehicle mode only) solves your CURRENT
  stops with both methods in parallel (`compareMethods()` in
  `templates/click_router.html`) and draws both resulting routes on the
  map in distinct colors, with a table of drive time / free-flow baseline
  / savings-vs-click-order / solve time for each and which one actually
  came out faster on this specific instance — a measurement of one
  concrete case, explicitly NOT presented as "quantum always wins" (that
  claim would need `src/benchmark.py`'s aggregate-across-many-random-
  instances experiments, which is what those experiments are for; this
  panel's footnote says so). Deliberately non-committing: it draws into
  its own map layer and panel, and never touches `clickedPoints`,
  `lastSolveContext`, or the main route/directions/live-reopt state, so
  running a comparison can't be confused with (or interfere with) actually
  solving a route. Any precedence rules are sent to both sides; time
  windows are sent to the quantum-inspired side only, since classical has
  no notion of a position constraint and would otherwise 400 out the whole
  comparison. Covered by 3 Playwright tests in `tests/test_layout.py`
  (button enable/disable tracks point count and fleet mode, a real
  side-by-side solve renders both routes and the table without touching
  `lastSolveContext`, and — by intercepting `window.fetch` and inspecting
  the actual request bodies — time windows really are omitted from just
  the classical request).
- **Small credibility details:** an info icon next to the method selector
  explaining in plain language what "quantum-inspired" actually means
  (simulated annealing on a QUBO, on classical hardware — not real quantum
  hardware), and a "Quantum-inspired" badge in the header.

None of this changes what the app computes — it's the same OSRM +
congestion-model + QUBO pipeline described above. It changes whether a
judge experiences it as a hackathon prototype or a finished product.

