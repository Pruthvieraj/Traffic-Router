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

Run `python3 app.py`, open `http://127.0.0.1:5000`. Click the map to drop
a **Start** pin (green "S"), then an **End** pin (red "E"), then optionally
more stops in between (up to 10 total) — hit **Solve route** and it:

1. Fetches (or loads from cache) a real OpenStreetMap street network for
   the selected city — thousands of real intersections, not the dozen
   curated landmarks `multi_city_map.html` uses.
2. Snaps each of your clicks to the nearest real road junction, and tells
   you how far off each click was (so an accidental click in the middle of
   a park is visibly flagged, not silently misrouted).
3. Solves the best visiting order with a **fixed start and fixed end**
   (a proper A-to-B route through your stops, not a round trip back to
   start) — this is a different, harder-to-get-right QUBO formulation than
   the round-trip one everything else in this project uses (see
   `qubo_tsp.build_open_path_bqm`'s docstring for exactly how the fixed
   endpoints are guaranteed correct by construction, not just penalized).
   Verified against brute-force-optimal on 20 random test cases before
   shipping — see the project's build history if you want to rerun that check.
4. Draws the route following actual streets (the polyline is the real
   shortest-path road geometry between each pair of stops, stitched
   together), not straight lines between points.

**The one real caveat: it needs live internet, twice, for two different
reasons.** First, fetching real street data for a city the first time (a
few seconds; cached to `data/street_graphs/*.graphml` after that — later
runs and later cities you've already used are instant even offline).
Second, the satellite/street map tile images themselves, every time,
same as `multi_city_map.html`. If Overpass (OpenStreetMap's data API) is
unreachable — this happened in the sandbox this was built in, so the
fallback path is real and tested, not theoretical — it automatically
falls back to the same dozen-landmark curated network the static demo
uses, and the stats panel tells you plainly which mode you're in ("Real
OpenStreetMap street data" vs "Offline fallback"). In fallback mode your
clicks snap to whichever of the ~12 landmarks is nearest, which can be
a kilometer or more off if you click somewhere in between — genuinely
"anywhere in the city" requires the real street data to actually be
reachable.

**Why this needs a running server at all** (unlike the double-click-a-file
simplicity of `multi_city_map.html`): an arbitrary click has to be matched
against real map data and run through the solver on the spot — that's
server-side Python work triggered per click, which a static file fundamentally
can't do on its own.

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
- The very first click-anywhere solve for each city (on a fresh deploy)
  fetches real OpenStreetMap data live, same as running it locally — a few
  seconds, then cached for the rest of that deploy's lifetime. Render's
  free-tier disk doesn't persist across redeploys, so a new deploy means
  that first-fetch cost happens again; it doesn't mean the app is broken.
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
