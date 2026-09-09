"""
generate_before_after_chart.py
===============================
A single, honest "before vs after" chart for the SIH pitch deck's Impact
and Benefits slide: average route time when stops are visited in the
order they were clicked (no optimization) vs. the quantum-inspired
solver's optimized order, under the SAME simulated evening-peak traffic.

The number behind this chart is measured, not invented: 20 independently
seeded random 8-stop routes around the demo Bengaluru road network, at
6:30pm simulated traffic, each solved once with solve_quantum_inspired
and compared against the identical stops visited in their original
(unsorted) order. This mirrors exactly what /api/solve reports as
`savings_vs_naive_pct` for a real user's session — this chart is just
that same real metric, averaged over enough trials to be a defensible
headline number rather than a single lucky run.

Reproduce or change the trial count/city/hour by editing the constants
below and re-running:  python3 src/generate_before_after_chart.py
"""

import random

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from city_graph import build_demo_graph, CITIES
from congestion import apply_congestion
from distance_matrix import build_travel_time_matrix
from qubo_tsp import solve_quantum_inspired, tour_length

CITY = "Bengaluru"
HOUR = 18.5          # evening peak
N_STOPS = 8
N_TRIALS = 20
OUT_PATH = "../output/before_after_savings_chart.png"

# Palette — matches the pitch deck (generate_pitch_deck.js): deep indigo
# ink, violet accent, slate for the muted/"before" bar.
INK = "#1E1B4B"
VIOLET = "#7C3AED"
SLATE = "#94A3B8"
SLATE_TEXT = "#475569"


def measure_savings():
    G = build_demo_graph()
    Gc = apply_congestion(G, hour=HOUR)
    all_nodes = list(CITIES[CITY].keys())

    naive_costs, opt_costs, savings_pcts = [], [], []
    for seed in range(N_TRIALS):
        rng = random.Random(seed)
        waypoints = rng.sample(all_nodes, N_STOPS)
        W, _ = build_travel_time_matrix(Gc, waypoints)
        naive_tour = list(range(N_STOPS))  # as-clicked / unsorted order
        naive_cost = tour_length(naive_tour, W)
        result = solve_quantum_inspired(W, num_reads=500)
        opt_cost = result["cost"]
        naive_costs.append(naive_cost)
        opt_costs.append(opt_cost)
        savings_pcts.append((naive_cost - opt_cost) / naive_cost * 100)

    return {
        "avg_naive": float(np.mean(naive_costs)),
        "avg_opt": float(np.mean(opt_costs)),
        "avg_savings_pct": float(np.mean(savings_pcts)),
        "min_savings_pct": float(min(savings_pcts)),
        "max_savings_pct": float(max(savings_pcts)),
    }


def render_chart(stats: dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 6), dpi=200)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    categories = ["Before\n(as-clicked order)", "After\n(QubitRoute optimized)"]
    values = [stats["avg_naive"], stats["avg_opt"]]
    colors = [SLATE, VIOLET]

    bars = ax.bar(categories, values, width=0.5, color=colors, zorder=3)

    # Rounded data-ends: draw a small rounded cap at the top of each bar
    # rather than a hard rectangle edge.
    for bar in bars:
        bar.set_capstyle("round")

    # Direct value labels on each bar — no legend needed for 2 named categories.
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2, val + 45, f"{val:.0f} min",
            ha="center", va="bottom", fontsize=20, fontweight="bold", color=INK,
        )

    # The headline: a savings arrow/callout between the two bars. Ends short
    # of each bar top so the arrowhead never collides with the value labels
    # placed above them.
    y_arrow = max(values) * 0.55
    ax.annotate(
        "", xy=(1, stats["avg_opt"] + 30), xytext=(0, stats["avg_naive"] - 10),
        arrowprops=dict(arrowstyle="-|>", color=VIOLET, lw=2.5, shrinkA=0, shrinkB=0),
    )
    ax.text(
        0.5, y_arrow, f"−{stats['avg_savings_pct']:.0f}%\ntravel time",
        ha="center", va="center", fontsize=22, fontweight="bold", color=VIOLET,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor=VIOLET, linewidth=1.5),
    )

    ax.set_ylabel("Average route time (minutes)", fontsize=12, color=SLATE_TEXT)
    ax.set_ylim(0, max(values) * 1.4)
    ax.tick_params(axis="x", labelsize=13, colors=INK, length=0)
    ax.tick_params(axis="y", labelsize=10, colors=SLATE_TEXT)

    # Recessive frame: keep only a light baseline, drop the rest.
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.grid(False)

    ax.set_title(
        f"Optimized visiting order cuts average travel time by {stats['avg_savings_pct']:.0f}%",
        fontsize=15, fontweight="bold", color=INK, pad=18,
    )
    hour_int = int(HOUR)
    hour_label = f"{((hour_int - 1) % 12) + 1}:{int(round((HOUR % 1) * 60)):02d} {'PM' if hour_int >= 12 else 'AM'}"
    fig.text(
        0.5, 0.01,
        f"Avg. over {N_TRIALS} randomly-ordered {N_STOPS}-stop routes, {CITY}, simulated {hour_label} evening-peak traffic "
        f"(range: {stats['min_savings_pct']:.0f}%–{stats['max_savings_pct']:.0f}%) — reproducible via src/generate_before_after_chart.py",
        ha="center", fontsize=8.5, color="#94A3B8", style="italic",
    )

    fig.tight_layout(rect=[0, 0.035, 1, 1])
    fig.savefig(out_path, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    stats = measure_savings()
    print(stats)
    render_chart(stats, OUT_PATH)
    print(f"Wrote {OUT_PATH}")
