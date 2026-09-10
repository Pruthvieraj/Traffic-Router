# Patent Note

[← Back to README](../README.md)

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
`precedence` parameter, `src/clustering.py` — see [Precedence](live-app.md) above for
the honest scope of when a fleet split lets it apply), and
`tests/test_app.py::test_solve_precedence_and_incident_compose_in_one_request`
verifies precedence and incident-triggered re-optimization actually
compose in one request rather than only being tested independently.

Before filing anything: have a patent professional (your institution's IPR
cell, or a registered patent agent) re-run the novelty search specifically
against this narrowed Tier 2 claim — everything in this repo's own search
is a good-faith pass by a non-lawyer, not a substitute for one.
