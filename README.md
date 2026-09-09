# Quantum-Inspired Constraint-Aware Route Optimizer

[![tests](https://github.com/<your-username>/<repo-name>/actions/workflows/tests.yml/badge.svg)](https://github.com/<your-username>/<repo-name>/actions/workflows/tests.yml)

*(Replace `<your-username>/<repo-name>` above with your actual GitHub path once this is pushed — GitHub then renders a live, clickable "passing"/"failing" badge here, sourced from `.github/workflows/tests.yml`, which runs the full test suite below on every push. This is what turns "N tests passing" from a claim into something a judge can click and verify themselves.)*

Built for **SIH 2026 — PS SIH26137 "Quantum-Inspired Traffic Route Optimization"** (Egreen Quanta).

A working, runnable implementation: real road-network routing, congestion
that changes with time of day, a QUBO (Quadratic Unconstrained Binary
Optimization) formulation of the routing problem solved with a classical
simulated-annealing sampler that mimics quantum-annealing search behavior,
a classical baseline to compare against, and an honest benchmark of where
each one actually wins.

## Quick start

There are two ways to use this project — pick based on what you need:

**A) Fixed-landmark demo (no server, just double-click a file)** — 18
cities spanning every region of India, a dozen curated stops each,
everything precomputed:
```bash
pip install -r requirements.txt
python3 main.py
```
then open `output/multi_city_map.html` directly in your browser.

**B) Click-anywhere live routing (needs a running server)** — pick a
literally arbitrary start point, end point, and stops anywhere in the
city, on a real OpenStreetMap street network, solved on the spot:
```bash
pip install -r requirements.txt
python3 app.py
```
then open **http://127.0.0.1:5000** in your browser. This is the one that
actually answers "let me choose start/end anywhere in the city" — see
below for how it works and its one real caveat.

(`vendor/` holds a local copy of the Leaflet mapping library, used to build
both of the above fully offline — see below. You don't need to touch it.)

Everything runs offline (no API keys, no internet needed — see "Demo data"
below) and finishes in under a minute. Outputs land in `output/`:

| File | What it is |
|---|---|
| **`multi_city_map.html`** | **The flagship demo** — one page, a city dropdown covering 18 cities across India, a satellite/street basemap toggle, a classical-vs-quantum-inspired route toggle, and a "simulate disruption" button. Just double-click it. |
| `route_map.html` | Interactive map of a 6-stop Bengaluru delivery route at evening rush hour |
| `route_map_after_spike.html` | The same route re-optimized after a simulated accident/closure |
| `comparison_chart.png` | Experiment 1 chart: classical vs quantum-inspired (and Google OR-Tools, when installed) on plain routing |
| `constraint_chart.png` | Experiment 2 chart: single-constraint correctness — real, but not the whole patent story, see below |
| `report.md` | Full numeric results for all five experiments, in the wording used in the sections below |
| `experiment_1_unconstrained.csv`, `experiment_2_constrained.csv`, `experiment_3_composed.csv`, `experiment_4_multi_objective.csv`, `experiment_5_time_windows.csv` | Raw data behind the charts, Experiment 3's composed-vs-isolated numbers, Experiment 4's time-vs-distance trade-off numbers, and Experiment 5's time-window pruning-effectiveness numbers |
| `pitch_deck.pptx` | A 12-slide pitch deck, generated from the CSVs above — see "A pitch deck, generated from the project's own real numbers" below (run `node generate_pitch_deck.js` separately; not produced by `main.py` itself) |

### About `multi_city_map.html` — satellite maps and the multi-city toggle

This is the page to actually show judges. It ships with 18 cities baked
in, deliberately spread across the country rather than clustered around
one region — Bengaluru, Mumbai, Pune, Gurgaon, Noida, Delhi, Chennai,
Kolkata, Hyderabad, Ahmedabad, Jaipur, Lucknow, Chandigarh, Kochi, Bhopal,
Guwahati, Coimbatore, and Nagpur, covering North, South, East, West,
Central, and Northeast India — each with its own curated road network, congestion
pattern, and precomputed quantum-inspired / classical routes, all
switchable from one dropdown with no reload. The basemap toggle switches
between real satellite imagery and a street map, both upgraded for visual
quality: satellite is Esri World Imagery with Esri's "Boundaries and
Places" reference layer stacked on top (labels, roads, and place names
overlaid on the photo — plain satellite imagery alone is often
blurry/unlabeled outside major Indian metros, since real-world imagery
resolution isn't uniform everywhere), and the street layer is CARTO
Voyager rather than plain OpenStreetMap tiles — same free, no-API-key OSM
data underneath, but a noticeably crisper cartographic style with clearer
road hierarchy and label placement, plus retina (@2x) tiles for sharp
rendering on high-DPI screens. Same upgrade applied identically in
`templates/click_router.html` (the live app) and `src/visualize.py`'s
`route_map.html`, so every map in the project looks consistent.

Worth being precise about what this city list actually gates: it's the
map-centering dropdown and this offline curated-landmark demo only. The
live click-anywhere app (`app.py`, below) was never limited to these 18 —
real street routing (OSRM) and place search (Nominatim autocomplete) both
work anywhere in India, or the world, the instant you click the map or
type a search, regardless of which city is selected.

**One thing to know before you demo it: it needs live internet for the map
tiles.** The map library itself (Leaflet) and all the routing data are
fully embedded in the file — that part works completely offline, on a
laptop with wifi off, because this sandbox's own network is restricted
enough that I had to build and test it that way. But the satellite/street
*imagery* is fetched live from Esri/OpenStreetMap's tile servers — there's
no practical way to bundle real satellite tiles for 18 cities at every
zoom level into one file. So: bring your own hotspot as a backup if venue
wifi is a known problem, and if tiles fail to load, the road network,
routes, markers, and stats panel all still render fine on a blank
background — the demo doesn't break, it just loses the pretty backdrop.

**Adding another city** is one dictionary entry: open `src/city_graph.py`,
add `"Your City": {"Landmark A": (lat, lon), "Landmark B": (lat, lon), ...}`
to the `CITIES` dict (8+ landmarks recommended), then re-run
`python3 main.py` — the k-nearest-neighbor road-graph builder, the QUBO
solver, and the map all pick it up automatically, no other code changes.
The same new city entry also works for `app.py` below, since it reuses
`CITIES` for the city dropdown and center point.

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
exercised — see `src/analytics.py`. **Said plainly, because this is the
kind of thing that's easy to oversell:** this is an in-process counter, not
a database — it resets to zero on every restart (including Render
free-tier's spin-down/spin-up cycle), and it's per-worker-process (this
project's `Procfile` runs a single gunicorn worker, so in this specific
deployment the count really is complete, but it would silently fragment
across workers if you ever scaled that up without adding shared storage).
It stores no per-request data whatsoever — no IPs, no matrices, no
per-call timestamps, only aggregate counts — which is also exactly why it
needs no auth. `tests/test_app.py`'s analytics tests assert the counters
actually increment correctly per endpoint/method/flag and that the
response never grows extra fields beyond the documented aggregate set.

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
  and Bengaluru — see "About `multi_city_map.html`" above for the full
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

## Deploy to the cloud (a live URL, no laptop needed)

There are two genuinely different things people mean by "put it on the
cloud," and they need different amounts of work:

**Option A — the static demo via GitHub Pages, zero backend.**
`output/multi_city_map.html` is one self-contained file (Leaflet, the map
data, everything is already inlined into it). GitHub Pages only serves
static files straight to the browser — no Python running anywhere behind
it — which is exactly what this file needs. This is the fixed-landmark
version: no click-anywhere, no live solving, but it's genuinely a five
minute setup with nothing to maintain or pay for. A copy of it is already
included at the repo root as `index.html` (GitHub Pages looks for that name
by default), so:

1. Push this whole folder to GitHub (same `git init` / `add` / `commit` /
   `remote add origin` / `push` steps as Option B below).
2. On the repo's GitHub page: **Settings → Pages**.
3. Under "Build and deployment", set **Source** to "Deploy from a branch",
   pick branch **main** and folder **/ (root)**, then **Save**.
4. Wait about a minute, then refresh that same Settings → Pages screen —
   it'll show your live URL: `https://<your-username>.github.io/<repo-name>/`.
   That's it — no build step, no server, nothing to keep awake.

If you ever update the demo (say, more cities), just re-copy the new
`output/multi_city_map.html` over `index.html`, commit, and push — Pages
redeploys automatically within a minute or two.

**Option B — the real click-anywhere app, needs a Python host (GitHub
Pages cannot run this one).** GitHub
itself only stores code — it doesn't run anything. `app.py` is a live
Python/Flask process that has to actually be *running* somewhere to answer
clicks, so you need a separate host that runs Python for you. **Render** is
the easiest free option for this project. Steps:

1. **Push this folder to GitHub.** From inside this folder in Terminal:
   ```
   git init
   git add .
   git commit -m "Quantum-inspired traffic router for SIH 2026"
   ```
   Then create a new empty repository on github.com (no README/license —
   keep it empty), and run the two commands GitHub shows you on the new
   repo's page, which will look like:
   ```
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git branch -M main
   git push -u origin main
   ```
2. **Create a free Render account** at render.com and sign in with GitHub
   (this lets Render see your repos without you copying any tokens around).
3. **New + → Web Service**, pick this repo.
4. Render auto-detects Python. Confirm these settings (it usually gets them
   right from the files already in this repo, but check):
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** leave it — the included `Procfile` handles this
     (`gunicorn app:app`). If Render asks anyway, use that exact command.
   - **Instance type:** the free tier is enough for a hackathon demo.
5. Click **Deploy**. First build takes a few minutes (installing `osmnx`,
   `dwave-samplers`, etc.). When it's done you get a public URL like
   `https://your-app-name.onrender.com` — that's it, that's the live link,
   shareable with judges, works from any device.

**Two things worth knowing before you rely on this for a live demo:**
- Render's free tier spins the app down after ~15 minutes of no traffic,
  and the next visit takes ~30-50 seconds to wake back up. Open the link
  yourself a few minutes before you present so it's already warm.
- Real road-network routing (the OSRM calls) happens in the visitor's own
  browser now, not on Render's server, so it isn't affected by Render's
  disk resetting on redeploy or by cloud-IP rate-limiting the way an
  earlier version of this app was — see the `app.py` section above for
  why that changed.
- If you'd rather not deal with any of this by hand, Railway (railway.app)
  works almost identically to the Render steps above and is worth trying
  as a backup if Render's free-tier build ever times out on the heavier
  dependencies.

## What this project actually is

"Optimize traffic routing" is too broad to build in a few weeks, so this
implements one specific, real slice of it: **given a set of delivery/service
stops a vehicle must visit, and a road network whose travel times change
with congestion, find the best order to visit them in** — a classic
Traveling-Salesman-style routing problem, which is exactly how real
logistics dispatch systems reduce "optimize the route" down to something
solvable.

The pipeline:

1. **`src/city_graph.py`** — the road network. Ships with a small, offline,
   hand-built graph of real Bengaluru localities and approximate road
   distances, so the whole project runs with zero setup and no dependency
   on a live map API being reachable during a demo. Swap in a real
   OpenStreetMap network for any place with one function call — see
   "Using real map data" below.
2. **`src/congestion.py`** — turns the static road graph into a
   time-of-day-dependent one (rush-hour curve + per-road variation), and
   can inject a "spike" on specific roads to simulate an accident or
   closure — this is what the re-optimization demo uses.
3. **`src/distance_matrix.py`** — collapses the full road network down to
   just the pairwise travel times between the stops that actually matter
   (the delivery waypoints), each computed via Dijkstra over the current
   congested graph. This is what makes the next step tractable.
4. **`src/qubo_tsp.py`** — the core "quantum-inspired" piece. Formulates the
   waypoint-ordering problem as a QUBO (the standard representation used
   for D-Wave quantum annealers and QAOA) and solves it with
   `dwave.samplers.SimulatedAnnealingSampler` — a classical algorithm that
   searches the same energy landscape a quantum annealer would, so it's
   "quantum-inspired" without needing actual quantum hardware or a D-Wave
   account. Also supports adding real dispatch constraints (e.g. "pick up
   before drop-off") as extra penalty terms — this is the part that matters,
   see below.
5. **`src/baseline.py`** — a real classical baseline (nearest-neighbor
   construction + 2-opt local search) to compare against, plus a
   brute-force exact solver for small instances so we can measure "how far
   from truly optimal" each method gets.
6. **`src/ortools_baseline.py`** — an optional second, much stronger
   classical comparison point: Google OR-Tools' actual production routing
   solver, wired in the same shape as `baseline.py` so `benchmark.py` can
   drop it straight into Experiment 1. Not a required dependency — see its
   own docstring for why, and "The honest finding" below for what it adds.
7. **`src/benchmark.py`** + **`src/visualize.py`** — runs the two
   experiments below and produces the charts and report.
8. **`src/clustering.py`** — scales the fixed-endpoint solver past what a
   single QUBO can handle (see "Scaling past a dozen stops" below), and
   also implements the multi-vehicle dispatch demo (`solve_multi_vehicle`).
9. **`src/qaoa_solver.py`** — an optional second "quantum-inspired" solver
   for the same QUBO: QAOA, a gate-based variational quantum circuit,
   simulated classically via Qiskit instead of annealed. See "A second
   quantum computing paradigm" below for the full honest scope of what
   this does and doesn't prove.
10. **`src/traffic_provider.py`** — the pluggable interface between "a
   free-flow travel-time matrix" and "a congestion-adjusted one." Ships
   with the simulated model above AND a real, working live-traffic
   integration (`GoogleRoutesTrafficProvider`, `TRAFFIC_PROVIDER=google_routes`
   + your own `GOOGLE_ROUTES_API_KEY`) — see "Traffic-awareness" above for
   the full honest scope of what's genuinely wired up versus what still
   needs your own API key/credentials to run live.
11. **`src/qpu_solver.py`** — a real D-Wave quantum annealer as a first-class
   solver `method` (`method="qpu"`), alongside the classical/quantum-inspired
   methods above — see "Real quantum hardware validation" below for the
   full honest scope of what's genuinely wired up versus what needs your
   own D-Wave Leap account to run live.
12. **`src/explain.py`** — turns a solved route (or fleet split) into a
   plain-language, per-leg explanation (bottleneck leg, precedence checks,
   capacity margin), returned alongside every `/api/solve` and
   `/api/solve_fleet` response — see "Route explainability" below.
13. **`src/time_windows.py`** — position-range pruning for real clock-time
   arrival windows on top of the same QUBO — see "Time-window constraints"
   below for the full honest scope (a partial, disclosed answer, not a
   solved one).

## Automated tests

`tests/` has a pytest suite that enforces, in CI, the correctness claims
this README makes in prose rather than leaving them as one-time manual
checks — including the exact "verified against brute-force-optimal on
random trials" property claimed for the open-path solver below. Run it
with:

```
pip install pytest
pytest tests/ -v
```

**352 Python tests** (396 total including the layout suite below, plus a
separate 14-test Node.js frontend suite — see below), covering the QUBO
solver, the classical baselines, the multi-objective time/distance
trade-off (`combine_objectives`, real-vs-cosmetic-objective checks), route
explainability (`src/explain.py` — leg breakdowns, precedence-cost
attribution, per-vehicle capacity headroom), time-window position-pruning
(`src/time_windows.py` — the provable-bound rigor claims and the measured
pruning-helps-but-doesn't-guarantee gap), real-QPU wiring (`src/qpu_solver.py`
— decode/selection logic verified via an injected stand-in sampler, the
real no-token failure path checked unmocked), real-live-traffic wiring
(`src/traffic_provider.py`'s `GoogleRoutesTrafficProvider` — request
construction and response parsing verified via an injected fake HTTP
session, the real no-API-key failure path checked unmocked, plus the
`points`/`coords` plumbing through `/api/solve` and `/api/solve_fleet`),
the clustering/scaling logic,
the multi-vehicle dispatch demo (including the
real per-vehicle capacity cap — by stop count *or* by per-stop demand
weight — and its auto-raising of vehicle count in either mode), the
precedence ("visit X before Y") constraint on both the single-vehicle
open-path solver *and* the multi-vehicle dispatch demo (including that it
composes with incident-triggered re-optimization in a single request, and
that a precedence pair split across two vehicles by the fleet clustering
step fails as a clean 400 instead of a silently-wrong route), the
congestion model (including the on-demand incident spike), the pluggable
traffic-provider interface, the pan-India city data (every city has valid
India-bounded coordinates, enough landmarks for a real route, and a fully
connected road graph), the OpenAPI spec staying in sync with the real
Flask responses, an optional Google OR-Tools comparison suite
(`tests/test_ortools_baseline.py` — matches true brute-force optimal on
small instances, never scores below it, skips cleanly rather than failing
when `ortools` isn't installed), an optional QAOA comparison suite
(`tests/test_qaoa_solver.py` — same never-beats-true-optimal sanity bound,
plus reliably finding the true optimum on the tiny 1-2-interior-stop cases
small enough for both QAOA and brute force to be checked directly, skips
cleanly when `qiskit` isn't installed), and the live Flask endpoints —
including that a 20-stop
request (which the old 10-stop limit would have rejected) now succeeds
end-to-end, that the traffic-awareness fields come back correct for a
given simulated hour, that an incident spike can actually change the
chosen route order (not just the displayed number), and that
`/api/solve_fleet` assigns every stop to exactly one vehicle even under a
capacity constraint.

There's also a **14-test frontend suite** (`tests/frontend/`) for the
frontend logic that used to have zero coverage — the turn-by-turn
direction-building/formatting helpers, the "Live re-optimize" demo's
tick-by-tick decision logic (advancing simulated time, picking whether/
where to inject an incident, phrasing the live feed), and the fleet
analogue of that decision logic (`fleetOrderChanged` — did ANY vehicle's
own stop order change tick-to-tick, not just the fleet total) — all in
`static/route_helpers.js`. It needs only Node.js 18+ (its built-in test
runner, no npm install):

```
node --test tests/frontend/*.test.js
```

**And a 44-test real-browser layout suite** (`tests/test_layout.py`),
added after a real bug shipped through a fully green test suite and
several rounds of manual screenshots: the topbar had a fixed height
combined with `flex-wrap`, so on a narrower browser window its second row
of controls (Solve route, Clear points) rendered outside the bar, on top
of the map. Nothing above could have caught that — every other test
verifies *logic* (routes, costs, API responses), not what a real browser
actually paints. This suite launches the real `app.py` as a subprocess and
drives real Chromium against it via Playwright, asserting properties like
"no topbar control ever renders outside the topbar's own box" at five
different window widths (375px through 1920px) — and, to prove that's not
a tautology, temporarily reintroducing the original bug during development
confirmed these exact tests fail against it. It also locks in a few
frontend *interaction* behaviors the earlier unit tests couldn't reach
(multi-vehicle mode relabeling the first pin "Depot," the capacity input
only appearing once fleet mode is selected, the incident-simulate button
rendering once per stop, the city dropdown actually offering all 18
pan-India cities, the voice-search mic button rendering as a clean icon
rather than inheriting a stray dropdown-chevron background from the
topbar's generic button styling, the search fallback finding a broader
match for an address like "Sukhwani Gracia C" while still surfacing a
clear message when nothing is found anywhere, and the redesigned info-icon
tooltip showing/hiding correctly and staying fully on-screen at narrow
widths — several of these are real bugs this suite caught once during
development, not just properties it happened to already satisfy). Three of
these tests exercise the "Live re-optimize" demo end-to-end through a real
browser against the real running app: the button only enabling after a
successful solve, a live tick actually logging a real solved cost (not
just the immediate "started" notice), and clearing points stopping the
loop and disabling the button — with OSRM and map-tile requests stubbed
via Playwright's own request interception (the same pattern the search
tests above already use for Nominatim) rather than needing real network
access to those external services; `/api/solve` itself is reached at the
real local `app.py` and is never stubbed. Needs
Playwright, which — like pytest — is intentionally not in
`requirements.txt` (dev/CI-only, and the test file skips itself cleanly if
it's missing rather than failing the rest of the suite):

```
pip install playwright && playwright install --with-deps chromium
pytest tests/test_layout.py -v
```

All three suites run automatically on every push via
`.github/workflows/tests.yml` — that's the badge at the top of this
README. Worth running before a demo either way, and worth mentioning to
judges: the "verified" claims here are checked by an actual, continuously-run
test suite, not just narrated.

## Scaling past a dozen stops

The open-path QUBO's variable count grows with the *square* of the number
of interior stops, so a single QUBO stays fast and exact up to about a
dozen stops but doesn't scale indefinitely — a real dispatch route can
easily have 20-50 stops in a day. `src/clustering.py` implements the
standard "cluster-first, route-second" strategy real Vehicle Routing
Problem systems use at this scale: stops are split into small groups
(clustered directly on the travel-time matrix — no coordinates needed),
each group's visiting order is solved *exactly* with the same
brute-force-verified solver used everywhere else in this project, and the
groups are stitched together start-to-end.

`app.py`'s `/api/solve` now accepts up to `MAX_STOPS = 40` (up from 10)
via this path — below `CLUSTER_SIZE` (9) interior stops it's an exact
passthrough with identical behavior to before; above it, the response
includes `clusters_used > 1` and the UI's stats panel says so, honestly.
This is a **heuristic decomposition, not a guarantee of the global
optimum** above the threshold — worth saying plainly to judges, because
exact optimization of a 50-stop TSP is intractable for classical and
quantum approaches alike, and every real routing system at that scale
makes the same trade.

## The honest finding — please read this before pitching it

**Experiment 1 (plain routing, no constraints):** classical
nearest-neighbor + 2-opt matches or beats the QUBO + simulated-annealing
solver on both solution quality and speed, and the gap widens as the
number of stops grows. We tuned the penalty weighting and annealing sweep
count and this held up — it isn't a bug in this implementation, it's a
well-established result in operations research: 2-opt is a very strong
heuristic for small-to-medium metric TSP, and a generic QUBO/annealing
formulation doesn't beat it on the plain problem. **Do not claim this
project is "faster than classical routing" — a judge or an examiner who
tests it will find the same result we did, and an unsupported speed claim
is the fastest way to lose credibility in the Q&A.**

**This isn't just losing to a weak strawman, either.** When `ortools` is
installed (`pip install ortools` — an optional dependency, see
`src/ortools_baseline.py`), Experiment 1 also runs Google OR-Tools' actual
production routing solver — the same solver family behind real-world route
optimization products, not a hand-rolled student-project heuristic. It
finds the exact optimum on every instance small enough for brute force to
verify, and matches or beats the hand-rolled 2-opt baseline throughout.
Reporting that honestly matters: it rules out "maybe a stronger classical
baseline would've lost" as an excuse, and confirms the real story is what
Experiment 2 says — the quantum-inspired formulation's advantage shows up
once real constraints enter the problem, not on plain TSP where classical
local search (of any quality) already excels.

**Experiment 2 (routing with one real dispatch rule added) — this is the
actual claim:** real delivery dispatch always has rules beyond "shortest
path" — a pickup before its matching drop-off, a stop that must happen
before a cutoff, a road that's off-limits for a hazmat vehicle. We added
one such rule ("visit A before B") and compared:

- **Classical 2-opt**, which only knows about travel time and has no
  concept of the rule, so it violates the rule whenever violating it
  happens to be shorter — **in our test, 8 out of 15 random trials**.
  Patching the route after the fact to fix the violation cost an average
  of **+8.9% extra travel time**, and as much as **+43.8%** in the worst
  observed case.
- **The QUBO solver**, where the rule is one additional penalty term in
  the same optimization — it satisfied the rule **by construction, in all
  15 out of 15 trials**, because an assignment that violates it is
  mathematically penalized inside the same objective the solver is already
  minimizing, not checked afterward.

That gap — constraints satisfied by construction vs. bolted on with
per-rule repair code that still costs real distance — is real and
reproducible (`python3 src/benchmark.py` regenerates it). **Read it as one
ingredient, though, not the whole patent story:** a February 2026
peer-reviewed paper (Curuliuc & Leon, in
`Patent Filing Readiness Research.docx`) already describes this
same "constraint as penalty term ⇒ satisfied by construction" mechanism
for precedence specifically, so on its own this can't anchor a patent
claim. Experiment 3, next, is where the finding that's actually still open
gets measured.

**Experiment 2.5 → Experiment 3 (does solving multiple constraint types
*together* actually matter?):** single-constraint correctness — proven
above, and by that prior paper — doesn't imply a multi-vehicle dispatch
DECISION stays valid once a second constraint type enters the picture.
`src/benchmark.py`'s `run_experiment_3_composed()` takes the same
fleet-dispatch scenario and solves it three ways through the existing,
already-tested `solve_multi_vehicle` API: with demand-weighted vehicle
capacity AND a precedence rule enforced together (**COMPOSED**), with
capacity enforced but the solver never told about the precedence rule
(**CAPACITY-ONLY**), and with precedence enforced but the vehicle SPLIT
itself made without any awareness of demand (**PRECEDENCE-ONLY**). On a
reproducible 14-trial run:

- **COMPOSED** satisfied both precedence AND capacity in **14/14** trials.
- **CAPACITY-ONLY** (precedence-blind) happened to violate the precedence
  rule anyway in **6/14** trials.
- **PRECEDENCE-ONLY** (demand-blind split) put the two stops on
  **different vehicles entirely** in 1/14 trials — the split itself became
  incompatible with the rule, not just costly — and additionally
  **overloaded a vehicle beyond capacity** in **13/13** of the remaining
  trials, by as much as **+51.5%** over the limit.

That's the actual remaining, defensible claim: composing constraint types
into one fleet-dispatch decision — not any single constraint type in
isolation — is what guarantees the whole result stays valid, and neither
prior-art finding in the patent-readiness report covers that combination.
See `output/report.md`'s "Experiment 3" section and
`tests/test_benchmark.py` for the reproducible, regression-tested version
of this claim.

## Multi-objective routing — time vs. distance is a real trade-off, not two names for one number

Every route above optimizes for a single number: congested travel time. Real
dispatch also cares about road distance — a genuine proxy for fuel and
emissions cost, and one that doesn't move the same way time does once
congestion enters the picture (a route can be the fastest without being the
shortest, and vice versa). `src/qubo_tsp.py`'s `combine_objectives()` lets
the *same* QUBO solver minimize a weighted sum of several cost matrices —
`objectives=[(W_time, w), (W_distance, 1 - w)]` — with **zero changes** to
`build_tsp_bqm`/`build_open_path_bqm` themselves, because every QUBO term in
this project's formulation is already linear in the cost matrix, so a
weighted sum of matrices is just another cost matrix. `solve_quantum_inspired`
and `solve_open_path_quantum_inspired` both accept `objectives=` as a direct
alternative to `W=` (passing both, or neither, is an error), and return an
`"objective_breakdown"` — the winning tour's cost under each individual
objective matrix, not just the combined score.

Two things had to be true for this to be a real feature rather than a
cosmetic knob, and both are checked, not just asserted:

- **Exact equivalence at the extremes.** `objectives=[(W, 1.0)]` must
  produce a byte-identical tour and cost to plain `W=W`, and
  `objectives=[(W1, 1.0), (W2, 0.0)]` must exactly recover the `W1`-only
  solve — not "close," `==`. `tests/test_multi_objective.py` asserts this
  with `==`, not `pytest.approx`, because that equivalence is the entire
  reason no change was needed to the QUBO-construction functions.
- **A genuine trade-off in the underlying problem**, not just in the
  solver's math. `src/benchmark.py`'s `run_experiment_4_multi_objective()`
  finds the *true* fastest tour and the *true* shortest tour for random
  waypoint sets by exhaustive search (`baseline.brute_force_optimal` — no
  simulated-annealing noise), then measures what optimizing for only one
  objective actually costs on the other. On a reproducible 12-trial run:
  optimizing for only one objective provably cost something on the other in
  **7/12** trials (average +1.0% extra distance / +0.8% extra time when it
  happened, worst case +1.9% / +2.4%). The other 5 trials happened to tie —
  reported honestly as ties, not folded into the "diverged" count.

Run `python3 src/benchmark.py` to regenerate `output/experiment_4_multi_objective.csv`
and the "Experiment 4" section of `output/report.md`; run
`python3 -m pytest tests/test_multi_objective.py tests/test_benchmark_experiment4.py`
to re-verify both properties above. **Not yet wired up:** the live app
(`app.py`) still solves for time only — `objectives=` is implemented and
tested at the solver/benchmark level, but there's no UI control yet to let a
user pick a time/distance weighting for a live route.

## Route explainability — why does the route look like this?

A solver that just hands back a list of stop indices leaves the real
questions unanswered: which leg of the trip is actually costing the most
time, is a business rule actually being honored (and by how much margin),
and — if it isn't obviously being honored — what would it have cost to
enforce it anyway? `src/explain.py` answers these by interpreting an
already-solved route, not by changing how routes are solved: it adds no new
solver logic and nothing about `qubo_tsp.py`/`clustering.py` changed for
this.

- **`explain_path(path, W, ...)`** — a leg-by-leg cost breakdown of any
  solved path (a single-vehicle open path, or one vehicle's closed
  depot-loop): each leg's cost and share of the total, the single
  most-expensive ("bottleneck") leg, and, when a `precedence` list is
  passed, a per-rule check of whether it's satisfied and at exactly which
  positions in the route.
- **`explain_precedence_impact(W, precedence, ...)`** — the per-instance
  version of what `benchmark.py`'s Experiment 2 measures in aggregate:
  solves the *same* instance with and without a precedence rule (both via
  the unchanged `solve_quantum_inspired`) and reports the real extra cost
  of enforcing it on *this specific* route, not an average across many
  random trials.
- **`explain_fleet(result, W, ...)`** — the multi-vehicle version: each
  vehicle's own leg breakdown, its remaining capacity headroom (when
  `demands`/`vehicle_capacity` were used for the solve), and which vehicle
  owns each precedence rule and whether that vehicle's own route satisfies
  it.

All three are covered by `tests/test_explain.py` (12 tests) — checked
against independently recomputed totals and percentages, not trusted as a
black box.

**Already wired into the live app:** both `/api/solve` and
`/api/solve_fleet` now return an `"explanation"` field built from the route
they just solved (see `app.py`) — covered by 4 tests in `tests/test_app.py`.
**Now rendered in the UI too:** a collapsible "Why this route?" panel in
the stats sidebar (`_explanationHtml()` in `templates/click_router.html`)
shows the bottleneck leg, per-rule precedence checks, and — in fleet
mode — each vehicle's own breakdown plus its capacity headroom, computed
from that vehicle's own path positions rather than the combined fleet's.
Also shown alongside it: each time-window rule's real checked outcome
(`_timeWindowChecksHtml()` — see "Time-window constraints" below) and a
clearly-labeled-as-an-estimate fuel/CO2 figure (`_fuelCo2Html()`, generic
average-petrol-car constants disclosed as such, not measured for any real
vehicle). **Honest gap:** `explain_precedence_impact`'s before/after
comparison still isn't called from either endpoint, since it means a
second solve (real added latency for a live click) — it's available as a
library function and demonstrated in `tests/test_explain.py`, not yet
exposed as its own API route or UI control.

## Time-window constraints — a partial, honestly-scoped answer, not a solved one

Real dispatch often has a real clock-time requirement — "the pharmacy pickup
must happen between 9am and 11am." This is the roadmap's highest
formulation-risk item, and the reason why is structural: `qubo_tsp.py`'s
QUBO encodes a tour as `x[v, t] = 1` iff waypoint `v` is at tour POSITION
`t`, not at any particular clock time — and a position-based QUBO has no
direct way to penalize "arrive after 11:00," because arrival time at
position `t` isn't a fixed function of `t` alone, it depends on which
specific edges the eventual tour uses to get there. Encoding TRUE wall-clock
windows exactly needs a different formulation family (arc-based decision
variables plus a time-propagation constraint per edge, e.g. an MTZ-style
scheme) — a genuinely bigger rewrite than this project's other constraint
additions (precedence, capacity, position windows), and `src/time_windows.py`
does **not** attempt that rewrite. It does something smaller, real, and
honestly bounded instead:

- **`derive_position_window(W, window)`** converts a real clock-time window
  into a tour-POSITION range that's *provably safe* to enforce: reaching
  position `t` always costs at least the sum of the `t` smallest edges in
  `W` and at most the sum of the `t` largest (summing any `t` distinct
  numbers can never beat the globally smallest `t`, or exceed the globally
  largest `t`) — so any position whose best-case cost already exceeds the
  window, or whose worst-case cost never reaches it, is mathematically
  impossible for *any* tour, not just the one eventually found. Excluding
  only those positions can never discard a solution that could have
  satisfied the window.
- **`qubo_tsp.add_position_window_penalty`** enforces that derived range as
  a hard QUBO constraint — the same mechanism as precedence, wired through
  a new `position_windows=` parameter on `build_tsp_bqm` /
  `build_open_path_bqm` / both solve functions (backward compatible: omitted
  by default, verified via `test_build_tsp_bqm_without_position_windows_is_unchanged`).
- **`compute_arrival_schedule` + `check_time_windows`** compute the REAL
  cumulative arrival time of whatever tour the solver actually returns and
  check it against the requested window — the ground truth this whole
  module is honest about needing, since the pruning above is necessary but
  not sufficient.
- **`solve_with_time_windows(...)`** ties all three together: derive safe
  bounds, solve with them enforced, verify the real result, and report
  exactly which windows (if any) are still violated.

**Measured, not just argued (`benchmark.py`'s Experiment 5, 15 trials, each
window deliberately shifted earlier than where the target waypoint landed
with no constraint at all, so it's a genuine ask):** without any
time-awareness, the unconstrained solve happened to satisfy the window in
**0/15** trials; with position-window pruning enforced, it was satisfied in
**3/15** trials. **Pruning helps — it never does worse than no time-
awareness at all (locked in by `test_with_pruning_never_does_worse_than_without_pruning`)
— but it is not a guarantee**, and the numbers say so plainly: two tours can
share the same allowed position for the target waypoint while arriving
there at very different real times, because the position bound only rules
out placements that could never work for *any* tour, not placements that
simply didn't pan out for the specific tour found. Run
`python3 src/benchmark.py` to regenerate `output/experiment_5_time_windows.csv`
and see the "Experiment 5" section of `output/report.md`; run
`python3 -m pytest tests/test_time_windows.py tests/test_benchmark_experiment5.py`
(19 tests) to re-verify the rigor claims and the measured gap above.

**Now wired into the live app and the UI.** `/api/solve` accepts an
optional `time_windows` field (`{"point_index": [earliest, latest]}`,
minutes from the Start point) — see app.py's `_validate_time_windows` and
`solve()`, which converts each window to a position bound via
`derive_position_window` against the ACTUAL congested matrix about to be
solved on, solves, then verifies the real result via
`compute_arrival_schedule`/`check_time_windows` and returns
`time_window_checks`/`all_time_windows_satisfied` — never just the pruning
guarantee. Same honest scope as everywhere else this restriction applies:
`method="quantum"`/`"qpu"` only (classical 2-opt has no notion of a
position constraint), and only up to `CLUSTER_SIZE` interior stops (7
tests in `tests/test_app.py`, 4 in `tests/test_clustering.py`). The
click-map UI's "Time windows" panel (`templates/click_router.html`,
mirroring the existing Precedence panel's UI pattern) lets you author
these rules directly — pick a stop, set an earliest/latest minute, Add —
and the checked outcome (met/missed, with slack or how much it missed by)
renders inside the "Why this route?" explanation panel after solving. Only
in single-vehicle mode, since `/api/solve_fleet` doesn't accept this
field. Covered by 4 Playwright layout tests in `tests/test_layout.py`
(add/remove a rule, reject an invalid range, hide in fleet mode, and the
remap/drop-on-removal helpers). Stated plainly because it's still the
honest conclusion of Experiment 5 above: **this is not a wall-clock
time-window guarantee** — it is real, tested, rigorous pruning that
measurably helps and is now checked against the real solved schedule on
every request, with the true reformulation needed for an unconditional
guarantee left as explicit future work rather than something this
iteration claims to have solved.

## Real quantum hardware validation (optional, but a strong differentiator)

Every result described above — and everything the live app uses by
default — solves the QUBO with classical simulated annealing standing in
for a quantum annealer ("quantum-inspired"). That's an honest and
defensible foundation, but it's also what almost every other "quantum" SIH
project does, because it's free and needs no special access.

`src/qpu_solver.py` makes a real D-Wave quantum annealer a **first-class
solver mode**, not a one-off side script: `method="qpu"` now works
everywhere `method="quantum"` and `method="classical"` already do —
`clustering.solve_open_path_scalable`, `clustering.solve_multi_vehicle`,
and both live API endpoints (`/api/solve`, `/api/solve_fleet` — see
`openapi.yaml`'s `method` enum). Every `"qpu"` call builds the IDENTICAL
BQM `"quantum"` builds (`qubo_tsp.build_tsp_bqm` / `build_open_path_bqm` —
same objective, same precedence/position-window support) and submits it to
`dwave.system.EmbeddingComposite(DWaveSampler())` instead of classically
simulating one. `run_on_real_quantum_hardware.py` now calls into this same
module too, rather than keeping its own separate hardware-submission logic
to duplicate and drift.

**This is the one item in the "10/10" punch list that genuinely can't be
done for you** — actually running on hardware needs *your* D-Wave Leap
account and API token, which no one else can supply. It's 5 minutes,
though:

1. Sign up free at <https://cloud.dwavesys.com/leap/> (no credit card).
2. `pip install dwave-system` (deliberately NOT in `requirements.txt` —
   see the comment there — since it's the one dependency this project
   doesn't need unless you want real hardware).
3. Grab your API token from the Leap dashboard (top right, "API Token"),
   then: `export DWAVE_API_TOKEN="your-token-here"`
4. Either `python3 run_on_real_quantum_hardware.py` for the pitch-deck
   artifact (a comparison table + `output/real_quantum_hardware_result.md`,
   quote or screenshot it when a judge asks "is this actually quantum, or
   just named that"), or pass `"method": "qpu"` to `/api/solve` /
   `/api/solve_fleet` for a live, real-hardware-backed solve in the app
   itself — or, now, just pick "Real QPU (D-Wave annealer)" from the
   click-map UI's method dropdown directly (it was API-only before; the
   dropdown previously only offered Quantum-inspired/Classical even though
   the backend already supported `qpu` everywhere).

**Without a token configured** (this project's default, and this
sandbox's own actual state while building this feature — the failure
below is real, not simulated for documentation purposes), selecting
`method="qpu"` fails with a clear, caught error rather than a crash —
`dwave-system`'s own `"API token not defined"` surfaces as a clean HTTP
400 from the live app, or a plain printed message from the script. Nothing
silently falls back to simulated annealing and pretends it ran on
hardware.

**Real hardware has real limits this project is upfront about.** A QPU
chip has a fixed qubit count and a sparse physical connectivity graph,
unlike a classical simulator's "as many variables as fit in RAM" — this
project's QUBO couples every waypoint pair (fully connected), which real
hardware has to embed onto its sparser graph. `qpu_solver.py` enforces a
conservative `MAX_QPU_INTERIOR_STOPS` cap (8) and raises a clear error
above it — a documented, honest guess at "small enough to be worth
trying" rather than a verified guarantee, since actual embeddability isn't
something this project can check without hardware access. A larger
`/api/solve` request that needs multiple clusters (see "Scaling past a
dozen stops" below) with `method="qpu"` submits ONE REAL hardware job per
cluster — genuinely real each time, but worth knowing before pointing a
30-stop request at your monthly QPU-second allotment.

**Tested without needing hardware or a token** (`tests/test_qpu_solver.py`,
11 tests, plus 2 in `tests/test_app.py`): every solve function accepts an
optional `sampler=` override used only by tests to inject a lightweight
stand-in exposing the same `.sample(bqm, num_reads=...)` interface real
D-Wave samplers do (dwave-samplers' own `SimulatedAnnealingSampler`, which
already speaks that interface) — this verifies the actual wiring (decode,
best-feasible-read selection, precedence/position-window filtering, the
size cap) is correct, the same way a payment integration's request-
building logic gets tested without an actual real charge. The "no
credentials configured" failure path is tested for real, unmocked, since
this sandbox genuinely has no token.

**Honest gap:** the frontend (`templates/click_router.html`) doesn't offer
`"qpu"` as a selectable method yet — its method dropdown still only shows
"classical" and "quantum" (simulated annealing). `method="qpu"` reaches
the API and works end to end (curl it, or use `run_on_real_quantum_hardware.py`),
it just isn't wired into that UI control yet.

## A second quantum computing paradigm: QAOA (optional, no account needed)

Everything above — annealing (simulated or real D-Wave hardware) — is one
half of how quantum computing research approaches combinatorial
optimization. The other major paradigm is **gate-based variational
circuits**, and QAOA (the Quantum Approximate Optimization Algorithm) is
the standard one for exactly this kind of problem. `src/qaoa_solver.py`
takes the same `build_open_path_bqm` QUBO the live app and the annealing
solver both already use, converts it to Ising form (`dimod`'s own
BINARY→SPIN conversion — no hand-derived coefficients), and builds the
actual QAOA circuit explicitly (alternating cost/mixer unitaries as
`RZ`/`RZZ`/`RX` gates, written out rather than hidden behind a framework
call) using Qiskit's current V2 primitives. No account or hardware access
needed — `pip install qiskit` and run:

```
python3 run_qaoa_demo.py
```

This prints brute-force-optimal, classical 2-opt, simulated annealing, and
QAOA side by side for a small 5-point route, and writes
`output/qaoa_demo_result.md` for your slides. On the runs we've done, QAOA
matches the true optimum on this small instance — worth having in the
pitch as "the same QUBO formulation ports directly to a second quantum
computing paradigm with zero reformulation," which is a real, checkable
technical point.

**Said as plainly as everywhere else in this README:** this runs on a
*classical simulation* of a quantum circuit, not real quantum hardware —
simulating an n-qubit statevector costs `O(2^n)`, so this is only
practical up to roughly 3-4 interior stops (9-16 qubits) before simulation
itself becomes the bottleneck, independent of whether QAOA is "working."
At the shallow circuit depths tractable here (p=1-2), QAOA is not claimed
to beat simulated annealing in general — published results on generic
QUBOs agree low-depth QAOA is a comparatively weak optimizer, and nothing
here disputes that. It also isn't wired into the live app: a
circuit-simulation-per-request model doesn't fit a stateless HTTP
request/response cycle at any size worth showing a real user. Read
`src/qaoa_solver.py`'s docstring for the full version of every caveat
above, and `tests/test_qaoa_solver.py` for what's actually verified (valid
results never beat the true brute-force optimum; on tiny 1-2-interior-stop
instances where brute force is trivial, QAOA reliably finds it).

## A pitch deck, generated from the project's own real numbers

`generate_pitch_deck.js` builds `output/pitch_deck.pptx` — a 12-slide,
fully-designed deck (title, the problem, the 5-step pipeline, both quantum
paradigms, both benchmark experiments with a real chart, multi-vehicle
dispatch, a feature grid, the test/CI numbers, the patent angle, roadmap,
and a closing slide) — directly from this project's own regenerated
benchmark CSVs, not hand-typed numbers copy-pasted once and left to drift.
Run it after `main.py` so the CSVs it reads are current:

```
python3 main.py
npm install        # one-time — pulls in pptxgenjs, the only Node dependency here
node generate_pitch_deck.js
```

That writes `output/pitch_deck.pptx`, ready to open in PowerPoint or
Google Slides. Every number on the two benchmark slides — the Experiment 1
chart and Experiment 2's `15/15` / `8/15` / `+31.9%` stat callouts — is
read straight out of `output/experiment_1_unconstrained.csv` and
`output/experiment_2_constrained.csv`, computed the same way
`src/benchmark.py`'s own `summarize_and_save()` does, so the deck can
never claim a number the benchmark script and test suite don't actually
produce. Re-run both commands any time the benchmark, feature set, or test
count changes, and the deck regenerates in sync rather than going stale.

**Honest gap:** `generate_pitch_deck.js` doesn't have Experiment 3, 4, or 5
slides yet — it still only reads the two original CSVs. The
composed-constraint numbers are real and in `output/experiment_3_composed.csv`,
the time-vs-distance trade-off numbers are real and in
`output/experiment_4_multi_objective.csv`, and the time-window
pruning-effectiveness numbers are real and in
`output/experiment_5_time_windows.csv`, but all three are currently
something you'd add to the deck by hand (or ask for slides to be generated
from those CSVs the same way) rather than something the script produces
automatically.

## How to pitch this at your internal round / to SIH judges

Lead with Experiment 2, not Experiment 1. The narrative: *"Off-the-shelf
routing heuristics are excellent at the textbook problem, but real
logistics dispatch always has business rules layered on top, and that's
exactly where they break down — we measured an X% violation rate and up to
44% wasted distance from patching a classical router after the fact. Our
QUBO-based formulation bakes each new rule in as one more term in the same
optimization, so it's correct by construction, and the same framework is
the one the field is actively porting to real quantum annealing hardware
as these problems scale."* Then show the `route_map.html` /
`route_map_after_spike.html` live re-optimization demo — a moving map is
more convincing in the room than any chart.

If a judge asks "why doesn't this already exist" — this is your answer:
classical routing engines (Google's OR-Tools, most commercial dispatch
software) DO handle constraints, but by hand-coding a specific solver
variant per constraint type (a capacitated-VRP solver, a VRP-with-time-windows
solver, etc.) — each is its own bespoke algorithm. The pitch here is a
single, uniform mathematical formulation (QUBO) where *any* new constraint
is just another penalty term, which is both simpler to extend and is the
same representation the quantum-computing-for-logistics research
community (D-Wave, IBM Qiskit optimization) is targeting for future
hardware acceleration — so this isn't a dead-end classical trick, it's
positioned on that trajectory.

If the follow-up question is sharper — "isn't 'encode a constraint as a
penalty term' already known?" — that's exactly right, and Experiment 3
is the answer, not Experiment 2: single-constraint correctness is known
prior art (say so, don't dodge it — see the prior-art memo). What isn't
covered is that composing multiple constraint types into one live
fleet-dispatch decision is what keeps the WHOLE result valid — Experiment
3 measures a demand-blind split overloading a vehicle in effectively every
trial where a precedence-blind solve would have gotten it right. That's a
stronger, more specific answer than repeating the Experiment 2 numbers
again.

## Extending this before the real pitch

Several items that used to be listed here as "the natural next step" are
now actually built — said honestly, because half the value of a list like
this is knowing which half is done:

- **More constraint types** — precedence ("visit X before Y"), multiple
  vehicles, real per-stop demand weights, a second optimization objective
  (time vs. distance — see "Multi-objective routing"), and real numeric
  time-window penalties (see "Time-window constraints") are all live,
  tested, and wired into the QUBO. What's NOT done: enforcing precedence
  or time windows across cluster boundaries once a problem is large enough
  to need `clustering.py`'s split-and-stitch (both are scoped, in their
  own sections above, to "within a single QUBO's stop count").
- **Real quantum hardware** — `src/qpu_solver.py` submits the SAME BQM to
  a real D-Wave QPU via `method="qpu"`, a first-class option everywhere
  `method="quantum"`/`"classical"` already work (see "Real quantum
  hardware validation"). What's NOT done, because it can't be from here:
  actually running it, which needs your own free D-Wave Leap account and
  API token — this sandbox has neither, so the wiring is tested via a
  dependency-injected stand-in sampler and this sandbox's own real,
  unmocked "no token configured" failure, not a live hardware run.
- **Real live traffic** — `src/traffic_provider.py`'s
  `GoogleRoutesTrafficProvider` is a real, working integration with
  Google's Routes API (see "Traffic-awareness"). What's NOT done: running
  it live, same reason as the QPU above (needs your own
  `GOOGLE_ROUTES_API_KEY` and Google Cloud billing setup) — AND the
  UVH-26 vehicle-density-calibration path below, which is a genuinely
  different, still-open idea (calibrating the *simulated* model from real
  images, rather than replacing it with a live API).
- **Continuous re-optimization** — the "Live re-optimize" topbar toggle
  (see "Continuous re-optimization") repeatedly re-solves against a
  simulated clock, not a real live feed, in BOTH single-vehicle and fleet
  mode (fleet-mode support was added after the section above was first
  written — see "Fleet mode is now covered too" there). What's NOT done:
  anything resembling a real vehicle's live GPS position feeding back into
  the loop (there is no real vehicle here to track), and precedence rules
  in the fleet-mode loop (the manual fleet solve itself doesn't send them
  yet either).
- **Using real map data**: `src/city_graph.py` has `build_live_osm_graph()`
  using `osmnx` to pull an actual OpenStreetMap road network for any place
  name — swap it in for `build_demo_graph()` once you've confirmed your
  venue has reliable internet (Overpass API calls can be slow/rate-limited,
  which is exactly why the offline demo graph is the default). Note this
  is a DIFFERENT layer than `TRAFFIC_PROVIDER`: this is road *geometry*,
  that's *congestion* on top of it.
- **Calibrating congestion from real imagery**: `src/congestion.py`'s
  synthetic rush-hour model is still a placeholder in its own right (a
  separate, still-open idea from the `google_routes` live-API path above
  — this one calibrates the SIMULATED model's numbers rather than
  replacing it). IISc's **UVH-26** dataset
  (https://huggingface.co/datasets/iisc-aim/UVH-26) — 26,646 annotated
  Bengaluru traffic-camera images across 2,800 CCTV cameras, released
  November 2025 — is a strong, free, real-Indian-data source: running a
  vehicle-density pass on even a handful of its images to calibrate a few
  junctions' congestion multipliers would meaningfully strengthen the "real
  data" story in your pitch. Nobody has done this yet in this project.

## Patent note

Two research documents cover this — read
**`Patent Filing Readiness Research.docx`** first; it supersedes the
patent-facing framing in the earlier `Idea Research Report.docx`,
which was written before a closer prior-art pass.

**The short version:** a follow-up novelty search found a February 2026
peer-reviewed paper (Curuliuc & Leon, *Applied Sciences*) that already
describes the exact mechanism this project's constraint code relies on —
encoding a routing constraint directly as a QUBO penalty term so it's
satisfied *by construction* rather than filtered after the fact
(`add_precedence_penalty()` / `build_open_path_bqm` in `src/qubo_tsp.py`).
**That mechanism on its own is not a patentable finding — do not write a
provisional claim headlined by it.** What's left to realistically claim
(the research doc's "Tier 2" scope) is the specific *system*: a live,
traffic-congestion-aware QUBO router where precedence, demand-weighted
per-vehicle capacity, multi-vehicle dispatch, and on-demand incident
re-optimization all compose together in one working pipeline, not each
sitting alone as an isolated feature. That composed claim had to actually
be *true in the code* before it could honestly go in a filing — it now is:
precedence works in multi-vehicle mode too (`solve_multi_vehicle`'s
`precedence` parameter, `src/clustering.py` — see "Precedence" above for
the honest scope of when a fleet split lets it apply), and
`tests/test_app.py::test_solve_precedence_and_incident_compose_in_one_request`
verifies precedence and incident-triggered re-optimization actually
compose in one request rather than only being tested independently.

Before filing anything: have a patent professional (your institution's IPR
cell, or a registered patent agent) re-run the novelty search specifically
against this narrowed Tier 2 claim — everything in this repo's own search
is a good-faith pass by a non-lawyer, not a substitute for one.
