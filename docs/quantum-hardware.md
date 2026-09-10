# Real Quantum Hardware & QAOA

[← Back to README](../README.md)

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
account and API token, which no one else can supply, on both a local run
and a deployed one (Render, etc.). `dwave-system` itself IS in
`requirements.txt` (so a fresh install/deploy already has the package —
this used to be an opt-in extra, back when only the standalone
`run_on_real_quantum_hardware.py` script needed it; now the live app's
"Real QPU" dropdown option needs it too), but the package alone doesn't
turn real hardware on.

**Correction, and this matters:** an earlier version of this section said
signing up was free and took 5 minutes. That was wrong — checked against
D-Wave's own current support docs while debugging exactly this with a
user, not assumed. As of D-Wave's own help center (checked September
2026): the self-serve **Trial plan you get from signing up at
<https://cloud.dwavesys.com/leap/> genuinely does NOT include an API
token** — Trial (and, per a Feb 2025 support update, Developer) plan
accounts can only run D-Wave's own pre-built demos from the Leap
dashboard, not submit their own jobs via `DWaveSampler`/`dwave-system`,
which is exactly what this project's `method="qpu"` needs. An API token
that actually works requires a **paid** Leap customer plan — see
<https://cloud.dwavesys.com/leap/plans> for current pricing, which
isn't published in a way this README can quote reliably (it's account/
quote-driven) — or D-Wave's application-based **Leap Quantum
LaunchPad** program (aimed at businesses/academic institutions,
advertised as a 3-month free trial; worth checking if your institution
qualifies, but it's an application process, not instant self-serve
signup: <https://www.dwavequantum.com/quantum-launchpad/>).

If you do get a working token (paid plan, LaunchPad, or otherwise), the
mechanics are unchanged:

1. Grab your API token from the Leap dashboard (top right, "API Token") —
   if you don't see one there at all, that's D-Wave's own signal that
   your current plan doesn't include API access.
2. Set it as `DWAVE_API_TOKEN` wherever the app actually runs:
   - **Local run:** `export DWAVE_API_TOKEN="your-token-here"` in the same
     shell before `python3 app.py`.
   - **Render (or another host):** your terminal's `export` only reaches
     your own machine — a deployed server needs the token set in *its own*
     environment. On Render: your service → **Environment** tab → **Add
     Environment Variable** → key `DWAVE_API_TOKEN`, value your token →
     save, which redeploys the service. (Other hosts have an equivalent
     "environment variables" or "secrets" settings page.)
3. Either `python3 run_on_real_quantum_hardware.py` for the pitch-deck
   artifact (a comparison table + `output/real_quantum_hardware_result.md`,
   quote or screenshot it when a judge asks "is this actually quantum, or
   just named that"), or pass `"method": "qpu"` to `/api/solve` /
   `/api/solve_fleet` for a live, real-hardware-backed solve in the app
   itself — or just pick "Real QPU (D-Wave annealer)" from the click-map
   UI's method dropdown directly.

**If you don't get/can't afford a token:** that's a legitimate place to
land, and worth saying to judges plainly rather than glossing over — the
QPU integration itself is real, tested, and not a stub (see
`tests/test_qpu_solver.py`'s 11 tests, which exercise the actual
`dwave.system` code paths via an injected stand-in sampler, plus the
real "no token configured" failure path checked unmocked, not skipped).
What's gated behind a paid account is only the literal act of submitting
a job to physical hardware and getting a chip ID/annealing-time back —
everything else (the identical BQM construction, the decode/selection
logic, the clean error handling) is already built and verifiable without
paying anything.

If you've done all of the above (real token, on a plan that actually
includes API access) on a deployed app and `method="qpu"` still fails:
check that specific service's build log to confirm `dwave-system`
actually installed, and double check the environment variable is spelled
exactly `DWAVE_API_TOKEN` and attached to the same service that's
actually serving the request.

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

