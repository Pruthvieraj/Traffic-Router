"""
qaoa_solver.py
==============
A second, genuinely different "quantum-inspired" solver for the exact same
fixed-start/fixed-end QUBO this project already builds in
qubo_tsp.build_open_path_bqm — this time solved with QAOA (the Quantum
Approximate Optimization Algorithm), a gate-based variational quantum
circuit, instead of simulated annealing.

WHY THIS IS A DIFFERENT THING, NOT A DUPLICATE: everything else in this
project labeled "quantum-inspired" (qubo_tsp.py's SimulatedAnnealingSampler
path) is a classical algorithm that mimics quantum annealing's search
behaviour — it never builds a quantum circuit at all. QAOA is the OTHER
major paradigm quantum computing research targets for combinatorial
optimization: a parameterized quantum circuit (alternating "cost" and
"mixer" unitaries, built directly from this same QUBO's Ising form) whose
parameters are tuned by a classical optimizer in a loop, then sampled to
read off a candidate solution. This module actually builds and simulates
that circuit (via Qiskit's statevector simulator) — it is not calling a
library that hides the algorithm; the QAOA ansatz construction is written
out explicitly below specifically so it's inspectable and explainable in a
Q&A, not a black-box call.

IMPLEMENTED FROM QISKIT'S CIRCUIT PRIMITIVES DIRECTLY, not via the
`qiskit_algorithms.QAOA` convenience wrapper: that wrapper (and
qiskit-optimization's MinimumEigenOptimizer built on top of it) targets the
now-removed Qiskit V1 `Sampler` primitive and hasn't kept pace with
Qiskit's V2 primitives / 2.x releases at the time this was written, so
depending on it here would tie this project to an old, increasingly
unmaintained pin. Writing the ansatz and optimization loop directly against
`qiskit.primitives.StatevectorSampler` (stable, current Qiskit) means one
fewer fragile dependency, and — a real side benefit — the whole algorithm
is about 60 lines below instead of hidden behind a framework call.

**Honest scope, stated plainly, because QAOA is the part of this project
most likely to be oversold by a hackathon pitch if it isn't:**

1. This runs on a CLASSICAL STATEVECTOR SIMULATOR of a quantum circuit, not
   real quantum hardware. Every other caveat below assumes that context.
2. Simulating an n-qubit statevector costs O(2^n) memory/time — this is
   only practical for SMALL problems. The QUBO here has (n-2)^2 binary
   variables for n total points (see build_open_path_bqm), so this
   realistically tops out around 3-4 interior stops (9-16 qubits) on a
   laptop before simulation itself becomes the bottleneck — completely
   independent of whether QAOA "works" as an algorithm. This is a
   fundamental limit of simulating quantum circuits classically, not a
   limitation specific to this implementation.
3. p=1 (or even p=2-3) QAOA, the depths tractable here, is a genuinely
   weak optimizer compared to hundreds of simulated-annealing sweeps —
   the literature is clear that low-depth QAOA does not reliably
   outperform classical heuristics on generic QUBOs, and our own runs
   (see tests/test_qaoa_solver.py and run_qaoa_demo.py) do not claim
   otherwise. What this module demonstrates is that the SAME QUBO
   formulation this project already built for annealing is portable to a
   genuinely different quantum computing paradigm (gate-based circuits)
   with no reformulation needed — a real point in the "not tied to one
   quantum computing approach" pitch — not that QAOA wins.
4. Like `solve_open_path_quantum_inspired`, a sampled bitstring can be
   INFEASIBLE (violates the "exactly one stop per position" constraints) —
   more often than simulated annealing's hundreds of reads, since we only
   draw one optimization run's worth of shots here. This module reports
   that explicitly via the `valid` field rather than silently discarding
   or patching a bad result.
5. Not wired into the live click-router app (`/api/solve`) at all — a
   circuit-simulation-per-request model does not fit a stateless HTTP
   request/response cycle at any problem size that would actually
   interest a user, and pretending otherwise would be exactly the kind of
   overselling this project tries hard to avoid elsewhere. This is a
   research/demo module and a pitch-deck credibility artifact (see
   run_qaoa_demo.py), the same role run_on_real_quantum_hardware.py plays
   for real D-Wave hardware.

This is an OPTIONAL dependency (`qiskit`, `qiskit-optimization` is NOT
required — only plain `qiskit` and `scipy`, both already lightweight
compared to ortools) — deliberately not required by requirements.txt.
Install with:

    pip install qiskit
"""

import time

import dimod
import numpy as np
from scipy.optimize import minimize

from qubo_tsp import build_open_path_bqm, open_path_length, _decode_open_path

try:
    from qiskit import QuantumCircuit
    from qiskit.primitives import StatevectorSampler
    QISKIT_AVAILABLE = True
except ImportError:
    QISKIT_AVAILABLE = False


def _build_qaoa_circuit(h: dict, J: dict, num_qubits: int, reps: int, params: np.ndarray):
    """The QAOA ansatz, written out explicitly: H^{⊗n} to start in an equal
    superposition, then `reps` layers each alternating the cost unitary
    exp(-i*gamma*H_cost) — built directly from this QUBO's Ising
    coefficients (h_i single-qubit terms as RZ, J_ij two-qubit terms as
    RZZ) — with the mixer unitary exp(-i*beta*sum_i X_i) (RX on every
    qubit), before measuring in the computational basis."""
    gammas, betas = params[:reps], params[reps:]
    qc = QuantumCircuit(num_qubits)
    qc.h(range(num_qubits))
    for r in range(reps):
        gamma, beta = gammas[r], betas[r]
        for i, hi in h.items():
            qc.rz(2 * gamma * hi, i)
        for (i, j), jij in J.items():
            qc.rzz(2 * gamma * jij, i, j)
        qc.rx(2 * beta, range(num_qubits))
    qc.measure_all()
    return qc


def solve_open_path_with_qaoa(
    W: np.ndarray, start_idx: int, end_idx: int, reps: int = 1,
    shots: int = 512, final_shots: int = 4096, maxiter: int = 100, seed: int = 42,
) -> dict:
    """Solve the same fixed-start/fixed-end problem as
    solve_open_path_quantum_inspired, but via QAOA on a statevector
    simulator instead of simulated annealing. See this module's docstring
    for the full honest-scope explanation.

    Returns a dict shaped like the other solvers' results
    ({"path", "cost", "wall_seconds"}) plus two QAOA-specific fields:
    "valid" (False if the returned bitstring violates the QUBO's
    permutation constraints — see point 4 above; "path"/"cost" are then
    None) and "num_qubits" (how many binary variables the QUBO needed —
    the honest ceiling on how far this can scale on a simulator).

    Raises RuntimeError with an install hint if qiskit isn't available.
    """
    if not QISKIT_AVAILABLE:
        raise RuntimeError(
            "qiskit is not installed. It's an optional dependency used only for this "
            "alternative QAOA solver (not needed to run the app itself). "
            "Install with: pip install qiskit"
        )

    t0 = time.perf_counter()
    n = W.shape[0]
    middle = [v for v in range(n) if v not in (start_idx, end_idx)]

    if not middle:
        path = [start_idx, end_idx]
        return {
            "path": path, "cost": open_path_length(path, W), "valid": True,
            "wall_seconds": time.perf_counter() - t0, "num_qubits": 0, "best_energy": 0.0,
        }

    bqm = build_open_path_bqm(W, start_idx, end_idx)
    variables = list(bqm.variables)
    num_qubits = len(variables)
    var_index = {v: i for i, v in enumerate(variables)}

    # dimod's own BINARY->SPIN conversion — the standard x_i = (1-z_i)/2
    # substitution that turns this QUBO into the Ising-form (h, J)
    # coefficients a QAOA cost unitary is built from. Reusing dimod for
    # this (rather than re-deriving it by hand) means one less place a
    # sign error could creep in, and it's a library this project already
    # depends on for the simulated-annealing path.
    ising = bqm.change_vartype(dimod.SPIN, inplace=False)
    h = {var_index[v]: ising.linear[v] for v in variables}
    J = {(var_index[u], var_index[v]): coeff for (u, v), coeff in ising.quadratic.items()}

    sampler = StatevectorSampler(seed=seed)

    def _energy_of_bits(bits: str) -> float:
        sample = {variables[i]: int(bits[i]) for i in range(num_qubits)}
        return bqm.energy(sample)

    def _objective(params: np.ndarray) -> float:
        qc = _build_qaoa_circuit(h, J, num_qubits, reps, params)
        counts = sampler.run([(qc, [])], shots=shots).result()[0].data.meas.get_counts()
        total = 0.0
        for bitstring, count in counts.items():
            total += _energy_of_bits(bitstring[::-1]) * count  # qiskit bit order is reversed
        return total / shots

    rng = np.random.default_rng(seed)
    x0 = rng.uniform(0, np.pi, size=2 * reps)
    opt_result = minimize(_objective, x0, method="COBYLA", options={"maxiter": maxiter})
    best_params = opt_result.x

    # Standard QAOA post-processing: sample the optimized circuit again
    # (more shots this time, since we're reading off an answer rather than
    # estimating a gradient-free objective) and keep the single best
    # bitstring actually observed, not just the most probable one —
    # exactly how solve_open_path_quantum_inspired already picks the best
    # of num_reads samples rather than trusting the sampler's top pick.
    qc = _build_qaoa_circuit(h, J, num_qubits, reps, best_params)
    counts = sampler.run([(qc, [])], shots=final_shots).result()[0].data.meas.get_counts()
    best_bits, best_energy = None, float("inf")
    for bitstring, _count in counts.items():
        bits = bitstring[::-1]
        energy = _energy_of_bits(bits)
        if energy < best_energy:
            best_bits, best_energy = bits, energy

    wall_seconds = time.perf_counter() - t0
    sample = {variables[i]: int(best_bits[i]) for i in range(num_qubits)}
    path = _decode_open_path(sample, n, start_idx, end_idx, middle)

    if path is None:
        return {
            "path": None, "cost": None, "valid": False,
            "wall_seconds": wall_seconds, "num_qubits": num_qubits, "best_energy": best_energy,
        }
    return {
        "path": path, "cost": open_path_length(path, W), "valid": True,
        "wall_seconds": wall_seconds, "num_qubits": num_qubits, "best_energy": best_energy,
    }


if __name__ == "__main__":
    from city_graph import build_demo_graph
    from congestion import apply_congestion
    from distance_matrix import build_travel_time_matrix

    if not QISKIT_AVAILABLE:
        print("qiskit not installed — run: pip install qiskit")
    else:
        G = build_demo_graph()
        Gc = apply_congestion(G, hour=18.5)
        waypoints = ["Majestic", "Indiranagar", "Koramangala", "Jayanagar", "HSR Layout"]
        W, _ = build_travel_time_matrix(Gc, waypoints)
        result = solve_open_path_with_qaoa(W, 0, len(waypoints) - 1, reps=2)
        print(f"QAOA ({result['num_qubits']} qubits): valid={result['valid']}, "
              f"cost={result['cost']}, {result['wall_seconds']*1000:.0f} ms")
