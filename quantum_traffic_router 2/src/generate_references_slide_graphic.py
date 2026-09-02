"""
generate_references_slide_graphic.py
=====================================
A drop-in replacement graphic for the SIH template's "Research and
References" slide, which currently ships as one flat, undifferentiated
bullet list on a mostly-empty white slide (the #1 "boring slide" pattern
to avoid: no visual element, no hierarchy, uneven whitespace).

This groups the exact same references into four labeled categories as
cards with a colored icon badge — same content, no citation added or
removed except the one new, genuinely-used reference this project added
this session (Google OR-Tools, now a real benchmark dependency — see
src/ortools_baseline.py) — just organized so a judge can scan it in two
seconds instead of reading six lines top to bottom.

Colors intentionally echo the existing Canva template rather than this
project's own pitch-deck palette: navy/blue (matches the template's
footer bar), plus green/orange/purple accents already present in the SIH
logo and the template's own "QubitRoute" ellipse.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle

OUT_PATH = "../output/references_slide_graphic.png"

NAVY = "#1F5FA8"
GREEN = "#16A34A"
ORANGE = "#EA580C"
PURPLE = "#7C3AED"
INK = "#1E293B"
SLATE = "#475569"
BORDER = "#E2E8F0"

CARDS = [
    {
        "color": NAVY,
        "title": "Quantum Computing Tools",
        "lines": [
            "IBM Qiskit — qiskit.org",
            "(QAOA & optimization modules)",
            "D-Wave Ocean SDK — docs.ocean.dwavesys.com",
            "(QUBO formulation for routing problems)",
        ],
    },
    {
        "color": GREEN,
        "title": "Classical Benchmark Tools",
        "lines": [
            "Google OR-Tools —",
            "developers.google.com/optimization",
            "(production routing solver, used as our",
            "benchmark baseline)",
        ],
    },
    {
        "color": ORANGE,
        "title": "Research & Literature",
        "lines": [
            "arXiv — \"Potential Energy Savings from",
            "Quantum Computing-Based Route Optimization\"",
            "arXiv — \"Hybrid Quantum Optimization in the",
            "Context of Minimizing Traffic Congestion\" (2025)",
        ],
    },
    {
        "color": PURPLE,
        "title": "Government & Mapping Data",
        "lines": [
            "Smart Cities Mission, Govt. of India —",
            "smartcities.gov.in",
            "OpenStreetMap / Google Maps",
            "Platform API documentation",
        ],
    },
]


def render(out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(12.6, 5.6), dpi=200)
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 12.6)
    ax.set_ylim(0, 5.6)
    ax.axis("off")

    top_margin, bottom_margin, gap_y, gap_x = 0.2, 0.25, 0.3, 0.4
    card_w = 5.9
    card_h = (5.6 - top_margin - bottom_margin - gap_y) / 2
    top_row_y = 5.6 - top_margin - card_h
    bottom_row_y = top_row_y - gap_y - card_h
    positions = [
        (0.2, top_row_y),
        (0.2 + card_w + gap_x, top_row_y),
        (0.2, bottom_row_y),
        (0.2 + card_w + gap_x, bottom_row_y),
    ]

    for (x, y), card in zip(positions, CARDS):
        ax.add_patch(FancyBboxPatch(
            (x, y), card_w, card_h,
            boxstyle="round,pad=0,rounding_size=0.12",
            linewidth=1.2, edgecolor=BORDER, facecolor="white", zorder=2,
        ))
        # Icon badge
        badge_cx, badge_cy = x + 0.5, y + card_h - 0.5
        ax.add_patch(Circle((badge_cx, badge_cy), 0.28, facecolor=card["color"], edgecolor="none", zorder=3))
        ax.text(badge_cx, badge_cy, card["title"][0], ha="center", va="center",
                fontsize=17, fontweight="bold", color="white", zorder=4)
        # Title
        ax.text(x + 0.95, y + card_h - 0.5, card["title"], ha="left", va="center",
                fontsize=15, fontweight="bold", color=INK, zorder=4)
        # Reference lines
        line_y = y + card_h - 0.95
        for line in card["lines"]:
            ax.text(x + 0.35, line_y, line, ha="left", va="top",
                    fontsize=10.3, color=SLATE, zorder=4)
            line_y -= 0.32

    fig.tight_layout(pad=0.15)
    fig.savefig(out_path, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    render(OUT_PATH)
    print(f"Wrote {OUT_PATH}")
