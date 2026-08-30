# Quantum-Inspired Constraint-Aware Route Optimizer

Built for **SIH 2026 — PS SIH26137 "Quantum-Inspired Traffic Route Optimization"** (Egreen Quanta).

A working, runnable implementation: real road-network routing, congestion
that changes with time of day, a QUBO (Quadratic Unconstrained Binary
Optimization) formulation of the routing problem solved with a classical
simulated-annealing sampler that mimics quantum-annealing search behavior,
a classical baseline to compare against, and an honest benchmark of where
each one actually wins.

## Quick start

There are two ways to use this project — pick based on what you need:

**A) Fixed-landmark demo (no server, just double-click a file)** — five
cities, a dozen curated stops each, everything precomputed:
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
| **`multi_city_map.html`** | **The flagship demo** — one page, a city dropdown (Bengaluru / Mumbai / Pune / Gurgaon / Noida), a satellite/street basemap toggle, a classical-vs-quantum-inspired route toggle, and a "simulate disruption" button. Just double-click it. |
| `route_map.html` | Interactive map of a 6-stop Bengaluru delivery route at evening rush hour |
| `route_map_after_spike.html` | The same route re-optimized after a simulated accident/closure |
| `comparison_chart.png` | Experiment 1 chart: classical vs quantum-inspired, plain routing |
| `constraint_chart.png` | Experiment 2 chart: the one that actually matters — see below |
| `report.md` | Full numeric results, in the wording used in the sections below |
| `experiment_1_unconstrained.csv`, `experiment_2_constrained.csv` | Raw data behind both charts |

### About `multi_city_map.html` — satellite maps and the multi-city toggle

This is the page to actually show judges. It ships with five cities baked
in — Bengaluru, Mumbai, Pune, Gurgaon, Noida — each with its own curated
road network, congestion pattern, and precomputed quantum-inspired /
classical routes, all switchable from one dropdown with no reload. The
basemap toggle switches between real satellite imagery (Esri World
Imagery) and a plain OpenStreetMap street layer.

**One thing to know before you demo it: it needs live internet for the map
tiles.** The map library itself (Leaflet) and all the routing data are
fully embedded in the file — that part works completely offline, on a
laptop with wifi off, because this sandbox's own network is restricted
enough that I had to build and test it that way. But the satellite/street
*imagery* is fetched live from Esri/OpenStreetMap's tile servers — there's
no practical way to bundle real satellite tiles for five cities at every
zoom level into one file. So: bring your own hotspot as a backup if venue
wifi is a known problem, and if tiles fail to load, the road network,
routes, markers, and stats panel all still render fine on a blank
background — the demo doesn't break, it just loses the pretty backdrop.

**Adding a 6th city** is one dictionary entry: open `src/city_graph.py`,
add `"Your City": {"Landmark A": (lat, lon), "Landmark B": (lat, lon), ...}`
to the `CITIES` dict (8+ landmarks recommended), then re-run
`python3 main.py` — the k-nearest-neighbor road-graph builder, the QUBO
solver, and the map all pick it up automatically, no other code changes.
The same new city entry also works for `app.py` below, since it reuses
`CITIES` for the city dropdown and center point.

## `app.py` — click anywhere in the city (real streets, real solve, live)

Run `python3 app.py`, open `http://127.0.0.1:5000`. Click the map — or
type a place name into the search box and pick it from the live
autocomplete suggestions — to drop a **Start** pin (green "S"), then an
**End** pin (red "E"), then optionally more stops in between (up to 10
total). Hit **Solve route** and it:

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
6. **`src/benchmark.py`** + **`src/visualize.py`** — runs the two
   experiments below and produces the charts and report.
7. **`src/clustering.py`** — scales the fixed-endpoint solver past what a
   single QUBO can handle (see "Scaling past a dozen stops" below).

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

48 tests, covering the QUBO solver, the classical baselines, the
clustering/scaling logic, and the live Flask endpoint (including that a
20-stop request — which the old 10-stop limit would have rejected — now
succeeds end-to-end). Worth running before a demo, and worth mentioning
to judges: the "verified" claims here are checked by an actual test suite,
not just narrated.

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
per-rule repair code that still costs real distance — is real,
reproducible (`python3 src/benchmark.py` regenerates it), and is the
concrete, measurable technical effect this project's patent description
should center on: **a routing optimizer in which additional real-world
dispatch constraints are incorporated as composable penalty terms within a
single QUBO formulation, guaranteeing constraint satisfaction by
construction, as compared to a measured tendency of unconstrained
classical local-search heuristics to violate such constraints and require
costly post-hoc repair.** That is a "concrete, measurable technical
effect" in the sense the 2025 CRI patent guidelines require — see the main
research report for the full patentability discussion.

## Real quantum hardware validation (optional, but a strong differentiator)

Every result described above — and everything the live app actually uses
— solves the QUBO with classical simulated annealing standing in for a
quantum annealer ("quantum-inspired"). That's an honest and defensible
foundation, but it's also what almost every other "quantum" SIH project
does, because it's free and needs no special access.

`run_on_real_quantum_hardware.py` takes the exact same QUBO
(`qubo_tsp.build_open_path_bqm` — the fixed-start/fixed-end formulation
the live app uses) and submits it to an actual D-Wave quantum annealer via
a free Leap cloud account, then prints/saves a side-by-side comparison
against brute-force-optimal, classical 2-opt, and the simulated-annealing
version. It needs a one-time free signup (no credit card) and `pip install
dwave-system` — full steps are in the script's own docstring. This is a
pitch-deck artifact (a real QPU chip ID, a real hardware timing number, a
real hardware result), not part of the live demo's normal code path — run
it once, save `output/real_quantum_hardware_result.md`, and quote or
screenshot it when a judge asks "is this actually quantum, or just named
that."

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

## Extending this before the real pitch

- **More constraint types**: add vehicle-capacity limits, time windows, or
  multiple vehicles by writing one more penalty-term function alongside
  `add_precedence_penalty()` in `qubo_tsp.py` — same pattern, same BQM.
- **Using real map data**: `src/city_graph.py` has `build_live_osm_graph()`
  using `osmnx` to pull an actual OpenStreetMap road network for any place
  name — swap it in for `build_demo_graph()` once you've confirmed your
  venue has reliable internet (Overpass API calls can be slow/rate-limited,
  which is exactly why the offline demo graph is the default).
- **Real congestion data**: `src/congestion.py`'s synthetic rush-hour model
  is a placeholder. IISc's **UVH-26** dataset
  (https://huggingface.co/datasets/iisc-aim/UVH-26) — 26,646 annotated
  Bengaluru traffic-camera images across 2,800 CCTV cameras, released
  November 2025 — is a strong, free, real-Indian-data source: running a
  vehicle-density pass on even a handful of its images to calibrate a few
  junctions' congestion multipliers would meaningfully strengthen the "real
  data" story in your pitch.
- **Real quantum hardware**: swap `SimulatedAnnealingSampler` for a real
  D-Wave `EmbeddingComposite(DWaveSampler())` (needs a D-Wave Leap account,
  free tier available) once problem sizes grow beyond what classical
  annealing handles comfortably — the QUBO you've already built
  (`build_tsp_bqm`) needs no changes to run on it.

## Patent note

See the main research report (`SIH_2026_Idea_Research_Heer.docx` /
`.md`) for the full patentability discussion and filing process. The one
addition after actually building this: **write your provisional patent's
Form 2 around the constraint-composability finding (Experiment 2), not a
speed/quality claim over classical routing** — that's the part that's
both true and defensible.
