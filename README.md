# Quantum-Inspired Constraint-Aware Route Optimizer

[![tests](https://github.com/Pruthvieraj/Traffic-Router/actions/workflows/tests.yml/badge.svg)](https://github.com/Pruthvieraj/Traffic-Router/actions/workflows/tests.yml)

*(Sourced from `.github/workflows/tests.yml`, which runs the full test
suite on every push. Shows "no status" until that file and `.gitignore`
are actually pushed to GitHub — both are git-tracked here, but a
drag-and-drop web upload can silently skip dotfiles/dotfolders. If the
badge is broken on your fork, check that repo's file list on GitHub.com
directly for a `.github` folder.)*

Built for **SIH 2026 — PS SIH26137 "Quantum-Inspired Traffic Route
Optimization"** (Egreen Quanta).

A working, runnable implementation: real road-network routing, congestion
that changes with time of day, a QUBO (Quadratic Unconstrained Binary
Optimization) formulation of the routing problem solved with a classical
simulated-annealing sampler that mimics quantum-annealing search behavior,
a classical baseline to compare against, and an honest benchmark of where
each one actually wins.

**This README covers the pitch, quick start, and honest findings. Deeper
technical write-ups live in [`docs/`](docs/) — linked throughout below.**

## Quick start

```bash
pip install -r requirements.txt
python3 main.py            # fixed-landmark demo, 18 Indian cities, no server
```
Open `output/multi_city_map.html` directly in your browser — that's the
flagship demo.

For the click-anywhere live version (pick any start/end/stops on a real
street network, solved on the spot):
```bash
python3 app.py
```
then open **http://127.0.0.1:5000**. See [`docs/live-app.md`](docs/live-app.md)
for exactly how it works, its live-traffic integration, precedence rules,
time windows, multi-vehicle dispatch, and its one real caveat (needs live
internet for map tiles and OSRM routing calls).

Everything runs offline otherwise (no API keys needed) and finishes in
under a minute. Key outputs in `output/`:

| File | What it is |
|---|---|
| `multi_city_map.html` | **The flagship demo** — 18 Indian cities, satellite/street toggle, classical-vs-quantum-inspired toggle, disruption simulation |
| `route_map.html` / `route_map_after_spike.html` | A 6-stop Bengaluru route, before/after a simulated incident |
| `comparison_chart.png`, `constraint_chart.png` | The two headline benchmark charts (see "Honest findings" below) |
| `report.md` | Full numeric results for all five experiments |
| `pitch_deck.pptx` | A 12-slide deck generated from the CSVs above — run `node generate_pitch_deck.js` separately, see [`docs/pitching.md`](docs/pitching.md) |

Adding a city is one dictionary entry in `src/city_graph.py`'s `CITIES`
dict, then re-run `python3 main.py` — see [`docs/architecture.md`](docs/architecture.md).

## What this project actually is

Given a set of delivery/service stops and a road network whose travel
times change with congestion, find the best order to visit them — a
classic TSP-style routing problem, solved by formulating it as a QUBO and
running classical simulated annealing (a "quantum-inspired" stand-in for a
real quantum annealer), with real dispatch constraints (precedence, per-
vehicle capacity, time windows, multi-objective time/distance) added as
extra penalty terms rather than bolted-on post-processing.

The full 13-module pipeline (road graph → congestion model → distance
matrix → QUBO solver → classical/OR-Tools baselines → clustering/scaling →
QAOA → live-traffic provider → real QPU solver → explainability →
time-window pruning) is documented file-by-file in
[`docs/architecture.md`](docs/architecture.md), including how it scales
past a dozen stops via cluster-first/route-second decomposition.

## Honest findings — please read this before pitching it

**Plain routing, no constraints:** classical nearest-neighbor + 2-opt
matches or beats the QUBO+simulated-annealing solver on both quality and
speed — a well-established OR result, not a bug here, and it holds even
against Google OR-Tools' real production solver when installed. **Do not
claim this project is "faster than classical routing."**

**Add one real dispatch rule (precedence):** classical 2-opt violated it
in **8/15** random trials (patching the route after the fact cost up to
**+43.8%** extra distance); the QUBO solver satisfied it **by
construction, 15/15**, because the rule is a penalty term inside the same
objective being minimized, not a post-hoc check. A Feb 2026 peer-reviewed
paper (Curuliuc & Leon) already describes this same mechanism, so **on its
own this can't anchor a patent claim** — see "Patent note" below.

**Compose multiple constraint types together (the actual remaining
claim):** solving capacity and precedence *together* satisfied both in
**14/14** trials; solving them separately let precedence-blind capacity
enforcement violate precedence in 6/14 trials, and demand-blind precedence
enforcement overload a vehicle by up to **+51.5%** in effectively every
remaining trial. Composing constraint types — not any one in isolation —
is what keeps a whole fleet-dispatch decision valid.

Full experiment-by-experiment numbers, the multi-objective (time vs.
distance) trade-off findings, and how to regenerate all of it: see
[`docs/benchmarks.md`](docs/benchmarks.md). Route explainability
(why a route looks the way it does) and the time-window pruning feature's
honest scope: [`docs/features.md`](docs/features.md).

## Automated tests

```bash
pip install pytest
pytest tests/ -v
```
**377 Python tests, 421 total** including a 44-test real-browser Playwright
layout suite (`pytest tests/test_layout.py -v`, needs
`pip install playwright && playwright install --with-deps chromium`),
plus a separate **14-test Node.js frontend suite**
(`node --test tests/frontend/*.test.js`). All three run automatically on
every push via `.github/workflows/tests.yml` — that's the badge at the
top of this README. Full breakdown of what's covered (including two real
bugs the layout suite caught during development that no logic-only test
could have): [`docs/testing.md`](docs/testing.md).

## Real quantum hardware (optional, a strong differentiator — and a real cost/gate, not a free 5-minute step)

`src/qpu_solver.py` submits the identical BQM to a real D-Wave quantum
annealer via `method="qpu"`, a first-class option everywhere
`"quantum"`/`"classical"` already work — tested via a dependency-injected
stand-in sampler (11 tests), not a stub. **Correction worth flagging
directly:** D-Wave's free self-serve Trial (and, per a Feb 2025 D-Wave
update, Developer) plan does **not** include an API token — only a paid
Leap plan or an accepted application to D-Wave's Leap Quantum LaunchPad
program does. Full setup, the exact env-var steps for a local run vs. a
deployed host, and what to say to judges if you don't get a token:
[`docs/quantum-hardware.md`](docs/quantum-hardware.md) (also covers the
QAOA gate-based alternative, no account needed).

## Deploy to the cloud

**Static demo, zero backend:** push to GitHub, enable **Settings → Pages**
on branch `main` / root — `index.html` (auto-kept in sync with
`output/multi_city_map.html` by `main.py`) is served automatically.
**Live click-anywhere app:** needs a Python host (GitHub Pages can't run
`app.py`) — Render's free tier is the easiest option. Full steps for both,
plus what to know about Render's free-tier spin-down before a live demo:
[`docs/deploy.md`](docs/deploy.md).

## Patent note

Read **`Patent Filing Readiness Research.docx`** first — a Feb 2026
peer-reviewed paper already describes the core "constraint as QUBO penalty
term" mechanism this project relies on, so **that mechanism alone is not
patentable; do not headline a filing with it.** What's left to realistically
claim is the composed *system* (precedence + capacity + multi-vehicle +
incident re-optimization all working together — see "Honest findings"
above). Full scope and the prior-art citation: [`docs/patent-note.md`](docs/patent-note.md).
Have a patent professional re-run the novelty search before filing
anything — this repo's own search is a good-faith non-lawyer pass.

## Pitching this at judging

Lead with the composed-constraints finding, not the plain-TSP one, and
show the live re-optimization demo — a moving map beats a chart in the
room. Full talking points, anticipated judge questions, and what's still
genuinely on the roadmap (real live-traffic calibration from IISc's
UVH-26 dataset, cross-cluster precedence, fleet-mode live traffic):
[`docs/pitching.md`](docs/pitching.md).

## License

[MIT](LICENSE) — see the LICENSE file. Business/IP documents
(`*.docx` patent-research files) are separate from the code license;
see "Patent note" above before treating any of that content as freely
reusable.

## Documentation index

All deep technical detail lives in [`docs/`](docs/), split out of this
README so it stays a quick pitch + quick-start, not a whitepaper:

- [`docs/live-app.md`](docs/live-app.md) — `app.py`'s full feature set and UI changelog
- [`docs/architecture.md`](docs/architecture.md) — the 13-module pipeline, and scaling past a dozen stops
- [`docs/benchmarks.md`](docs/benchmarks.md) — all 5 experiments in full, with exact numbers
- [`docs/features.md`](docs/features.md) — route explainability, time-window constraints
- [`docs/quantum-hardware.md`](docs/quantum-hardware.md) — real D-Wave QPU setup + QAOA
- [`docs/testing.md`](docs/testing.md) — what the 421+14 tests actually cover
- [`docs/deploy.md`](docs/deploy.md) — GitHub Pages and Render deployment steps
- [`docs/pitching.md`](docs/pitching.md) — pitch deck generation, judging talking points, roadmap
- [`docs/patent-note.md`](docs/patent-note.md) — the full patent-scope note
