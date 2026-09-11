# Pitch Deck, Pitching Guide & Roadmap

[← Back to README](../README.md)

## A pitch deck, generated from the project's own real numbers

`generate_pitch_deck.js` builds `output/pitch_deck.pptx` — a 15-slide,
fully-designed deck (title, the problem, the 5-step pipeline, both quantum
paradigms, all five benchmark experiments — Experiment 1 with a real chart,
Experiments 2-5 each with their own real stat cards — multi-vehicle
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
Google Slides. Every number on all five benchmark slides — the Experiment 1
chart, Experiment 2's `15/15` / `8/15` / `+31.9%` stat callouts, Experiment
3's composed-vs-isolated constraint numbers, Experiment 4's time/distance
trade-off percentages, and Experiment 5's pruning-vs-guarantee counts — is
read straight out of `output/experiment_{1..5}_*.csv`, computed the same
way `src/benchmark.py`'s own `summarize_and_save()` does (see
`generate_pitch_deck.js`'s own `exp3`/`exp4`/`exp5` aggregation, which
mirrors that function's logic field-for-field), so the deck can never claim
a number the benchmark script and test suite don't actually produce.
Re-run both commands any time the benchmark, feature set, or test count
changes, and the deck regenerates in sync rather than going stale.

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
  (time vs. distance — see [Multi-objective routing](benchmarks.md)), and real numeric
  time-window penalties (see [Time-window constraints](features.md)) are all live,
  tested, and wired into the QUBO. What's NOT done: enforcing precedence
  or time windows across cluster boundaries once a problem is large enough
  to need `clustering.py`'s split-and-stitch (both are scoped, in their
  own sections above, to "within a single QUBO's stop count").
- **Real quantum hardware** — `src/qpu_solver.py` submits the SAME BQM to
  a real D-Wave QPU via `method="qpu"`, a first-class option everywhere
  `method="quantum"`/`"classical"` already work (see "Real quantum
  hardware validation"). What's NOT done, because it can't be from here:
  actually running it, which needs your own D-Wave Leap API token from a
  plan that includes API access (see [Real quantum hardware validation](quantum-hardware.md)
  for why the free self-serve Trial plan doesn't qualify) — this sandbox
  has neither that plan nor a token, so the wiring is tested via a
  dependency-injected stand-in sampler and this sandbox's own real,
  unmocked "no token configured" failure, not a live hardware run.
- **Real live traffic** — `src/traffic_provider.py`'s
  `GoogleRoutesTrafficProvider` is a real, working integration with
  Google's Routes API, now verified end-to-end at the Flask level for
  BOTH `/api/solve` and `/api/solve_fleet` (a real injected provider
  monkeypatched in, asserting the returned route and cost, not just that
  the provider class works in isolation — see [Traffic-awareness](live-app.md)).
  What's NOT done: running it against the real, live, paid API, same
  reason as the QPU above (needs your own `GOOGLE_ROUTES_API_KEY` and
  Google Cloud billing setup) — AND the UVH-26 vehicle-density-calibration
  path below, which is a genuinely different idea (calibrating the
  *simulated* model from real images, rather than replacing it with a live
  API).
- **Continuous re-optimization** — the "Live re-optimize" topbar toggle
  (see [Continuous re-optimization](live-app.md)) repeatedly re-solves against a
  simulated clock, not a real live feed, in BOTH single-vehicle and fleet
  mode, and now sends precedence rules on every tick in both modes too
  (the manual fleet solve and the fleet-mode live-reopt loop both send
  them — see "Precedence" in [`docs/live-app.md`](live-app.md)). What's
  NOT done: anything resembling a real vehicle's live GPS position feeding
  back into the loop (there is no real vehicle here to track).
- **Using real map data**: `src/city_graph.py` has `build_live_osm_graph()`
  using `osmnx` to pull an actual OpenStreetMap road network for any place
  name — swap it in for `build_demo_graph()` once you've confirmed your
  venue has reliable internet (Overpass API calls can be slow/rate-limited,
  which is exactly why the offline demo graph is the default). Note this
  is a DIFFERENT layer than `TRAFFIC_PROVIDER`: this is road *geometry*,
  that's *congestion* on top of it.
- **Calibrating congestion from real imagery**: `src/congestion.py`'s
  synthetic rush-hour model is still a placeholder in its own right (a
  separate idea from the `google_routes` live-API path above — this one
  calibrates the SIMULATED model's numbers rather than replacing it).
  IISc's **UVH-26** dataset (https://huggingface.co/datasets/iisc-aim/UVH-26)
  — 26,646 annotated Bengaluru traffic-camera images across 2,800 CCTV
  cameras, released November 2025, COCO-format bounding boxes across 14
  Indian-traffic vehicle classes — is a strong, free, real-Indian-data
  source, and `src/vehicle_density_calibration.py` is a real, tested
  pipeline for turning exactly that annotation format into a congestion
  multiplier (vehicle-count extraction, a disclosed density-to-multiplier
  scale, and blending with the synthetic model), plus a runnable
  `calibrate_from_uvh26.py` CLI at the repo root. **What's genuinely still
  open, and why**: this project's own dev sandbox cannot download the
  90GB UVH-26 dataset to run that pipeline against real images — confirmed
  directly, huggingface.co and its CDN (and fallback hosts like GitHub)
  all get rejected at the network layer by this sandbox's egress policy,
  independent of the dataset being free. So the calibration LOGIC is real
  and tested (mirroring UVH-26's documented schema in its own test
  fixture), but nobody has run it against the actual dataset yet — that
  needs a machine with normal internet access, which this sandbox
  deliberately doesn't have. If you have internet access wherever you're
  reading this, you're one `pip install huggingface_hub` and a few
  minutes away from being the first to actually run it — see
  `calibrate_from_uvh26.py`'s docstring for the exact steps.

