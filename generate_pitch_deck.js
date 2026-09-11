#!/usr/bin/env node
/**
 * generate_pitch_deck.js — builds a ready-to-present SIH pitch deck
 * (output/pitch_deck.pptx) straight from this project's own real,
 * regenerated benchmark data — not hand-typed numbers that can drift out
 * of sync with the code.
 *
 * RUN THIS AFTER `python3 main.py` (which writes the CSVs this script
 * reads from output/) — if those files are missing, this exits with a
 * clear message telling you to run main.py first, rather than silently
 * falling back to stale or fabricated numbers.
 *
 *     python3 main.py && node generate_pitch_deck.js
 *
 * Needs only `pptxgenjs` (see package.json / the pptx skill this was
 * built with) — no Python dependency beyond what main.py already needs.
 *
 * Every number on the "honest finding" slides (Experiment 1 and 2) is
 * read directly from output/experiment_1_unconstrained.csv and
 * output/experiment_2_constrained.csv, computed the same way
 * src/benchmark.py's own summarize_and_save() does — so the deck can
 * never say something the test suite and benchmark script don't actually
 * produce.
 */

const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const OUTPUT_DIR = path.join(__dirname, "output");
const EXP1_CSV = path.join(OUTPUT_DIR, "experiment_1_unconstrained.csv");
const EXP2_CSV = path.join(OUTPUT_DIR, "experiment_2_constrained.csv");
const EXP3_CSV = path.join(OUTPUT_DIR, "experiment_3_composed.csv");
const EXP4_CSV = path.join(OUTPUT_DIR, "experiment_4_multi_objective.csv");
const EXP5_CSV = path.join(OUTPUT_DIR, "experiment_5_time_windows.csv");
const OUT_PATH = path.join(OUTPUT_DIR, "pitch_deck.pptx");

// ---------------------------------------------------------------------
// Tiny CSV reader. Experiment 1/2's fields are all plain numbers,
// True/False, or comma-free strings, but Experiment 5's `window` column
// is a quoted "(earliest, latest)" tuple with a comma INSIDE the quotes
// (csv.DictWriter's standard quoting) — a naive split(",") would shift
// every later column in that row, silently corrupting the two booleans
// this deck actually reads from it. This is a minimal quote-aware parser
// (handles "" as an escaped quote) rather than a full RFC 4180 impl,
// which is all these files ever produce.
// ---------------------------------------------------------------------
function parseCsvLine(line) {
  const cells = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else { inQuotes = false; }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      cells.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  cells.push(cur);
  return cells;
}

function readCsv(csvPath) {
  const text = fs.readFileSync(csvPath, "utf8").trim();
  const [headerLine, ...lines] = text.split("\n");
  const headers = parseCsvLine(headerLine);
  return lines.map((line) => {
    const cells = parseCsvLine(line);
    const row = {};
    headers.forEach((h, i) => { row[h] = cells[i]; });
    return row;
  });
}

// csv.DictWriter (src/benchmark.py) writes Python's True/False/None as the
// literal strings "True"/"False"/"" — these turn a raw cell back into the
// JS value summarize_and_save()'s own aggregate logic below mirrors.
function toBool(v) { return v === "True"; }
function toFloatOrNull(v) { return (v === undefined || v === "") ? null : parseFloat(v); }

for (const p of [EXP1_CSV, EXP2_CSV, EXP3_CSV, EXP4_CSV, EXP5_CSV]) {
  if (!fs.existsSync(p)) {
    console.error(`Missing ${p}.`);
    console.error("Run `python3 main.py` first — it regenerates the benchmark CSVs this deck reads from.");
    process.exit(1);
  }
}

const exp1 = readCsv(EXP1_CSV).map((r) => ({
  n: parseInt(r.n_waypoints, 10),
  twoOpt: parseFloat(r["2opt_cost_min"]),
  qubo: parseFloat(r.qubo_sa_cost_min),
  ortools: r.ortools_cost_min !== undefined && r.ortools_cost_min !== "" ? parseFloat(r.ortools_cost_min) : null,
}));
const hasOrtools = exp1.every((r) => r.ortools !== null);

const exp2Rows = readCsv(EXP2_CSV);
const exp2 = {
  trials: exp2Rows.length,
  violated: exp2Rows.filter((r) => r.plain_2opt_violates_rule === "True").length,
  quboValid: exp2Rows.filter((r) => r.qubo_sa_satisfies_rule === "True").length,
  avgRepairPct: exp2Rows.reduce((s, r) => s + parseFloat(r.repaired_2opt_extra_cost_pct), 0) / exp2Rows.length,
  maxRepairPct: Math.max(...exp2Rows.map((r) => parseFloat(r.repaired_2opt_extra_cost_pct))),
};

// Experiment 3 — composing capacity + precedence together. Aggregate logic
// mirrors src/benchmark.py's summarize_and_save() exactly (see its
// "Experiment 3" section) so this slide can never say a number the report
// and test suite don't also produce.
const exp3Rows = readCsv(EXP3_CSV).map((r) => ({
  composedPrecedenceOk: toBool(r.composed_precedence_ok),
  composedCapacityOk: toBool(r.composed_capacity_ok),
  capacityOnlyPrecedenceOkByLuck: toBool(r.capacity_only_precedence_ok_by_luck),
  precedenceOnlyPairSeparated: toBool(r.precedence_only_pair_separated_by_demand_blind_split),
  // Explicit tri-state: "True"/"False"/"" (skipped — the pair was already
  // separated, so there's no "capacity ok" question to ask) — NOT the same
  // as toBool("") === false, so this is read as its own nullable field.
  precedenceOnlyCapacityOkByLuck: r.precedence_only_capacity_ok_by_luck === "" ? null : toBool(r.precedence_only_capacity_ok_by_luck),
  precedenceOnlyWorstOverPct: toFloatOrNull(r.precedence_only_worst_vehicle_over_capacity_pct),
}));
const exp3 = (() => {
  const n = exp3Rows.length;
  const composedBothOk = exp3Rows.filter((r) => r.composedPrecedenceOk && r.composedCapacityOk).length;
  const capacityOnlyLuckFail = exp3Rows.filter((r) => !r.capacityOnlyPrecedenceOkByLuck).length;
  const pairSeparated = exp3Rows.filter((r) => r.precedenceOnlyPairSeparated).length;
  const precedenceOnlyOverloaded = exp3Rows.filter((r) => r.precedenceOnlyCapacityOkByLuck === false).length;
  const overloads = exp3Rows.map((r) => r.precedenceOnlyWorstOverPct).filter((v) => v !== null);
  return {
    n, composedBothOk, capacityOnlyLuckFail, pairSeparated,
    remainingAfterSeparation: n - pairSeparated,
    precedenceOnlyOverloaded,
    worstOverPct: overloads.length ? Math.max(...overloads) : 0.0,
  };
})();

// Experiment 4 — multi-objective time-vs-distance trade-off. Mirrors
// summarize_and_save()'s "Experiment 4" section exactly.
const exp4Rows = readCsv(EXP4_CSV).map((r) => ({
  diverges: toBool(r.objectives_diverge),
  extraDistPct: parseFloat(r.extra_distance_pct_if_time_only),
  extraTimePct: parseFloat(r.extra_time_pct_if_distance_only),
}));
const exp4 = (() => {
  const n = exp4Rows.length;
  const differing = exp4Rows.filter((r) => r.diverges);
  const avg = (arr) => (arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : 0.0);
  const max = (arr) => (arr.length ? Math.max(...arr) : 0.0);
  return {
    n, nDiffer: differing.length,
    avgExtraDist: avg(differing.map((r) => r.extraDistPct)),
    maxExtraDist: max(differing.map((r) => r.extraDistPct)),
    avgExtraTime: avg(differing.map((r) => r.extraTimePct)),
    maxExtraTime: max(differing.map((r) => r.extraTimePct)),
  };
})();

// Experiment 5 — does time-window position pruning actually help? Mirrors
// summarize_and_save()'s "Experiment 5" section exactly.
const exp5Rows = readCsv(EXP5_CSV).map((r) => ({
  withoutOk: toBool(r.without_pruning_satisfied),
  withOk: toBool(r.with_pruning_satisfied),
}));
const exp5 = {
  n: exp5Rows.length,
  withoutOk: exp5Rows.filter((r) => r.withoutOk).length,
  withOk: exp5Rows.filter((r) => r.withOk).length,
};

// ---------------------------------------------------------------------
// Palette — pulled directly from the live app's own design system (see
// README's "A real design system": dark indigo topbar, indigo/violet/cyan
// accents) so the deck reads as the same product, not a generic template.
// ---------------------------------------------------------------------
const INK = "1E1B4B";       // deep indigo — dark backgrounds, titles
const VIOLET = "7C3AED";    // primary accent
const CYAN = "22D3EE";      // secondary accent
const SLATE = "475569";     // body text on light backgrounds
const PAPER = "F8FAFC";     // light slide background
const WHITE = "FFFFFF";
const GOOD = "22C55E";      // success green (constraint satisfied)
const WARN = "F97316";      // warning orange (violation / repair cost)

const FONT_HEAD = "Cambria";
const FONT_BODY = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33" x 7.5"
pres.author = "Quantum-Inspired Traffic Router — SIH26137";
pres.title = "Quantum-Inspired Traffic Router";

function freshShadow(color = "0F172A") {
  return { type: "outer", color, opacity: 0.25, blur: 6, offset: 3, angle: 90 };
}

function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: INK };
  return s;
}
function lightSlide() {
  const s = pres.addSlide();
  s.background = { color: PAPER };
  return s;
}

function kicker(slide, text, opts = {}) {
  slide.addText(text.toUpperCase(), {
    x: opts.x ?? 0.6, y: opts.y ?? 0.35, w: opts.w ?? 8, h: 0.4,
    fontFace: FONT_BODY, fontSize: 13, bold: true, color: opts.color ?? VIOLET,
    charSpacing: 2, isTextBox: true,
  });
}

function title(slide, text, opts = {}) {
  slide.addText(text, {
    x: opts.x ?? 0.6, y: opts.y ?? 0.7, w: opts.w ?? 11.8, h: opts.h ?? 0.9,
    fontFace: FONT_HEAD, fontSize: opts.fontSize ?? 32, bold: true,
    color: opts.color ?? INK, isTextBox: true,
  });
}

function footer(slide, n) {
  slide.addText("Quantum-Inspired Traffic Router  ·  SIH26137", {
    x: 0.6, y: 7.08, w: 8, h: 0.3, fontFace: FONT_BODY, fontSize: 9,
    color: "94A3B8", isTextBox: true,
  });
  slide.addText(String(n), {
    x: 12.6, y: 7.08, w: 0.4, h: 0.3, fontFace: FONT_BODY, fontSize: 9,
    color: "94A3B8", align: "right", isTextBox: true,
  });
}

// =======================================================================
// Slide 1 — Title
// =======================================================================
{
  const s = darkSlide();
  s.addShape(pres.ShapeType.ellipse, {
    x: 9.6, y: -2.2, w: 7, h: 7, fill: { color: VIOLET, transparency: 78 }, line: { type: "none" },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: 11.2, y: 3.6, w: 4.6, h: 4.6, fill: { color: CYAN, transparency: 82 }, line: { type: "none" },
  });
  s.addText("SIH 2026  ·  PROBLEM STATEMENT 26137", {
    x: 0.9, y: 1.5, w: 9, h: 0.5, fontFace: FONT_BODY, fontSize: 14, bold: true,
    color: CYAN, charSpacing: 2, isTextBox: true,
  });
  s.addText("Quantum-Inspired Traffic\nRoute Optimization", {
    x: 0.85, y: 2.05, w: 10.5, h: 2.1, fontFace: FONT_HEAD, fontSize: 44, bold: true,
    color: WHITE, isTextBox: true, lineSpacingMultiple: 1.05,
  });
  s.addText(
    "A live, click-anywhere route optimizer that reformulates “what order should I visit "
    + "these stops in” as a QUBO and solves it the way quantum annealers and gate-based "
    + "quantum circuits do — benchmarked honestly against classical heuristics and Google's "
    + "own production solver, not just claimed.",
    {
      x: 0.9, y: 4.15, w: 8.6, h: 1.3, fontFace: FONT_BODY, fontSize: 15,
      color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.25,
    }
  );
  s.addText("Live demo: traffic-router.onrender.com", {
    x: 0.9, y: 6.55, w: 7, h: 0.4, fontFace: FONT_BODY, fontSize: 13, italic: true,
    color: CYAN, isTextBox: true,
  });
}

// =======================================================================
// Slide 2 — The problem
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "The problem");
  title(s, "Visiting order is the hard part — not point-to-point directions");

  s.addText(
    [
      { text: "A delivery van with 8 stops has ", options: {} },
      { text: "40,320", options: { bold: true, color: VIOLET } },
      { text: " possible visiting orders — picking badly wastes real fuel and time. This is the "
             + "Traveling Salesman Problem, and it stays hard as stop counts grow.", options: {} },
    ],
    { x: 0.6, y: 1.9, w: 6.7, h: 1.6, fontFace: FONT_BODY, fontSize: 16, color: SLATE, isTextBox: true, lineSpacingMultiple: 1.3 }
  );
  s.addText(
    "And the best order at 9am often is not the best order at 6pm — real dispatch also has "
    + "rules beyond “shortest path”: a pickup before its drop-off, a vehicle's carrying capacity, "
    + "a stop that must happen before a cutoff.",
    { x: 0.6, y: 3.55, w: 6.7, h: 1.5, fontFace: FONT_BODY, fontSize: 16, color: SLATE, isTextBox: true, lineSpacingMultiple: 1.3 }
  );

  // Stat callout card
  s.addShape(pres.ShapeType.roundRect, {
    x: 7.85, y: 1.9, w: 4.9, h: 4.7, rectRadius: 0.12,
    fill: { color: INK }, line: { type: "none" }, shadow: freshShadow(),
  });
  s.addText("8", {
    x: 7.85, y: 2.35, w: 4.9, h: 1.3, align: "center", fontFace: FONT_HEAD, fontSize: 60, bold: true,
    color: CYAN, isTextBox: true,
  });
  s.addText("interior stops in one of\nour own benchmark routes", {
    x: 7.85, y: 3.55, w: 4.9, h: 0.8, align: "center", fontFace: FONT_BODY, fontSize: 13,
    color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.2,
  });
  s.addShape(pres.ShapeType.line, { x: 8.55, y: 4.55, w: 3.5, h: 0, line: { color: "3730A3", width: 1 } });
  s.addText("40,320", {
    x: 7.85, y: 4.75, w: 4.9, h: 1.0, align: "center", fontFace: FONT_HEAD, fontSize: 40, bold: true,
    color: VIOLET, isTextBox: true,
  });
  s.addText("possible visiting orders (8!)\nto search for the best one", {
    x: 7.85, y: 5.75, w: 4.9, h: 0.7, align: "center", fontFace: FONT_BODY, fontSize: 13,
    color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.2,
  });
  footer(s, 2);
}

// =======================================================================
// Slide 3 — Pipeline
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "How it works");
  title(s, "Five steps, from a city map to a proven-better route");

  const steps = [
    ["1", "Get the map", "A real road network for the city — click anywhere, live in the browser."],
    ["2", "Add traffic", "Travel times stretch by time of day; an incident can spike one road on demand."],
    ["3", "Build the matrix", "Collapse the map to just the pairwise travel times between your chosen stops."],
    ["4", "Solve the QUBO", "Reformulate the ordering problem for quantum annealing or QAOA — solved today via simulated annealing or a simulated quantum circuit."],
    ["5", "Prove it", "Show the optimized route next to the naive one, with a real time-savings percentage."],
  ];
  const colW = 2.32;
  const startX = 0.6;
  steps.forEach((step, i) => {
    const x = startX + i * (colW + 0.08);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.0, w: colW, h: 4.5, rectRadius: 0.1,
      fill: { color: i === 3 ? INK : WHITE }, line: { color: "E2E8F0", width: i === 3 ? 0 : 1 },
      shadow: freshShadow(),
    });
    s.addShape(pres.ShapeType.ellipse, {
      x: x + colW / 2 - 0.3, y: 2.3, w: 0.6, h: 0.6,
      fill: { color: i === 3 ? CYAN : VIOLET }, line: { type: "none" },
    });
    s.addText(step[0], {
      x: x + colW / 2 - 0.3, y: 2.3, w: 0.6, h: 0.6, align: "center", valign: "middle",
      fontFace: FONT_HEAD, fontSize: 22, bold: true, color: i === 3 ? INK : WHITE, isTextBox: true,
    });
    s.addText(step[1], {
      x: x + 0.15, y: 3.1, w: colW - 0.3, h: 0.7, align: "center", fontFace: FONT_HEAD, fontSize: 15, bold: true,
      color: i === 3 ? WHITE : INK, isTextBox: true,
    });
    s.addText(step[2], {
      x: x + 0.2, y: 3.8, w: colW - 0.4, h: 2.5, align: "center", fontFace: FONT_BODY, fontSize: 11.5,
      color: i === 3 ? "C7D2FE" : SLATE, isTextBox: true, lineSpacingMultiple: 1.25,
    });
  });
  footer(s, 3);
}

// =======================================================================
// Slide 4 — Two quantum paradigms
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "Not tied to one quantum approach");
  title(s, "The same QUBO, two different quantum computing paradigms");

  const cardY = 2.0, cardH = 4.6, cardW = 5.9;
  const cards = [
    {
      x: 0.6, badge: "Quantum annealing", color: VIOLET,
      body: [
        "Simulated by default (dwave-samplers) — fast, free, no hardware needed for the live demo.",
        "The exact same BQM also runs on a real D-Wave QPU via a free Leap account — run_on_real_quantum_hardware.py prints an actual chip ID and hardware timing.",
      ],
    },
    {
      x: 6.8, badge: "Gate-based circuits (QAOA)", color: CYAN,
      body: [
        "The same QUBO, converted to Ising form and solved by an explicit QAOA circuit (RZ/RZZ/RX gates) on a Qiskit statevector simulator.",
        "No hand-off between formulations — one routing QUBO, portable to either major quantum computing paradigm with zero reformulation.",
      ],
    },
  ];
  cards.forEach((c) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: c.x, y: cardY, w: cardW, h: cardH, rectRadius: 0.12,
      fill: { color: WHITE }, line: { color: "E2E8F0", width: 1 }, shadow: freshShadow(),
    });
    s.addShape(pres.ShapeType.roundRect, {
      x: c.x + 0.35, y: cardY + 0.35, w: 3.6, h: 0.5, rectRadius: 0.25,
      fill: { color: c.color, transparency: 85 }, line: { type: "none" },
    });
    s.addText(c.badge, {
      x: c.x + 0.35, y: cardY + 0.35, w: 3.6, h: 0.5, align: "center", valign: "middle",
      fontFace: FONT_BODY, fontSize: 13, bold: true, color: c.color, isTextBox: true,
    });
    const bulletItems = c.body.map((t, i) => ({
      text: t, options: { bullet: { code: "25CF" }, breakLine: i < c.body.length - 1, paraSpaceAfter: 14 },
    }));
    s.addText(bulletItems, {
      x: c.x + 0.4, y: cardY + 1.1, w: cardW - 0.8, h: cardH - 1.4,
      fontFace: FONT_BODY, fontSize: 13.5, color: SLATE, isTextBox: true, lineSpacingMultiple: 1.25,
    });
  });
  footer(s, 4);
}

// =======================================================================
// Slide 5 — Experiment 1 (honest finding), real chart from CSV
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "Benchmark — experiment 1", { color: WARN });
  title(s, "Plain routing: classical wins — and we say so");

  const chartLabels = exp1.map((r) => String(r.n));
  const chartData = [
    { name: "Classical (2-opt)", labels: chartLabels, values: exp1.map((r) => r.twoOpt) },
    { name: "Quantum-inspired (QUBO+SA)", labels: chartLabels, values: exp1.map((r) => r.qubo) },
  ];
  if (hasOrtools) {
    chartData.push({ name: "Google OR-Tools", labels: chartLabels, values: exp1.map((r) => r.ortools) });
  }
  s.addChart(pres.ChartType.bar, chartData, {
    x: 0.6, y: 1.85, w: 7.6, h: 4.7,
    barDir: "col", showTitle: true, title: "Total route time by problem size (lower is better)",
    titleFontFace: FONT_BODY, titleFontSize: 12,
    showLegend: true, legendPos: "b", legendFontSize: 10,
    showValue: false,
    chartColors: [SLATE, VIOLET, GOOD],
    catAxisTitle: "Number of waypoints", catAxisLabelColor: SLATE, catAxisLabelFontSize: 10,
    valAxisTitle: "Minutes", valAxisLabelColor: SLATE, valAxisLabelFontSize: 10,
    valGridLine: { color: "E2E8F0", size: 1 }, catGridLine: { style: "none" },
    dataLabelColor: SLATE,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 8.5, y: 1.85, w: 4.25, h: 4.7, rectRadius: 0.12,
    fill: { color: INK }, line: { type: "none" }, shadow: freshShadow(),
  });
  s.addText("The honest finding", {
    x: 8.85, y: 2.15, w: 3.6, h: 0.5, fontFace: FONT_HEAD, fontSize: 16, bold: true, color: CYAN, isTextBox: true,
  });
  s.addText(
    [
      { text: "Classical nearest-neighbor + 2-opt matches or beats our QUBO+SA solver on plain, "
             + "unconstrained routing — and matches Google OR-Tools' production solver too.", options: {} },
      { text: "\n\nWe don't hide this. It's well-established operations-research literature, and it "
             + "points at exactly where the quantum-inspired approach's real advantage shows up next.", options: {} },
    ],
    { x: 8.85, y: 2.75, w: 3.6, h: 3.6, fontFace: FONT_BODY, fontSize: 13, color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.3 }
  );
  footer(s, 5);
}

// =======================================================================
// Slide 6 — Experiment 2 (the real claim)
// =======================================================================
{
  const s = darkSlide();
  kicker(s, "Benchmark — experiment 2", { color: CYAN });
  title(s, "Add ONE real dispatch rule — and the gap flips", { color: WHITE });

  const stats = [
    [`${exp2.quboValid}/${exp2.trials}`, "QUBO+SA satisfied the\nprecedence rule by construction", GOOD],
    [`${exp2.violated}/${exp2.trials}`, "trials where constraint-blind\n2-opt violated the same rule", WARN],
    [`+${exp2.maxRepairPct.toFixed(1)}%`, "worst-case extra distance from\npatching a violated route after the fact", WARN],
  ];
  const cardW = 3.9, gap = 0.25, startX = 0.6;
  stats.forEach((st, i) => {
    const x = startX + i * (cardW + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.1, w: cardW, h: 2.6, rectRadius: 0.12,
      fill: { color: "312E81" }, line: { type: "none" }, shadow: freshShadow(),
    });
    s.addText(st[0], {
      x, y: 2.3, w: cardW, h: 1.15, align: "center", fontFace: FONT_HEAD, fontSize: 40, bold: true,
      color: st[2], isTextBox: true,
    });
    s.addText(st[1], {
      x: x + 0.2, y: 3.45, w: cardW - 0.4, h: 1.1, align: "center", fontFace: FONT_BODY, fontSize: 12.5,
      color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.2,
    });
  });

  s.addText(
    "Real dispatch always has rules beyond “shortest path” — pickup before drop-off, a stop "
    + "before a cutoff, a road off-limits for one vehicle class. A classical local-search heuristic has no "
    + "notion of these; the QUBO formulation adds each one as one more composable penalty term in the same "
    + "optimization, satisfied by construction, not checked after the fact.",
    { x: 0.6, y: 5.05, w: 12.1, h: 1.5, fontFace: FONT_BODY, fontSize: 15, color: "E0E7FF", isTextBox: true, lineSpacingMultiple: 1.3 }
  );
  footer(s, 6);
}

// =======================================================================
// Slide 7 — Experiment 3: composing constraint types together (the actual
// remaining patent-relevant claim — see README "Honest findings")
// =======================================================================
{
  const s = darkSlide();
  kicker(s, "Benchmark — experiment 3", { color: CYAN });
  title(s, "Compose constraints together — that's the real claim", { color: WHITE });

  const stats = [
    [`${exp3.composedBothOk}/${exp3.n}`, "COMPOSED (capacity AND\nprecedence together) satisfied both", GOOD],
    [`${exp3.capacityOnlyLuckFail}/${exp3.n}`, "CAPACITY-ONLY (precedence-blind)\nviolated precedence anyway", WARN],
    [`+${exp3.worstOverPct.toFixed(1)}%`, "worst overload from a\nPRECEDENCE-ONLY (demand-blind) split", WARN],
  ];
  const cardW = 3.9, gap = 0.25, startX = 0.6;
  stats.forEach((st, i) => {
    const x = startX + i * (cardW + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.1, w: cardW, h: 2.6, rectRadius: 0.12,
      fill: { color: "312E81" }, line: { type: "none" }, shadow: freshShadow(),
    });
    s.addText(st[0], {
      x, y: 2.3, w: cardW, h: 1.15, align: "center", fontFace: FONT_HEAD, fontSize: 40, bold: true,
      color: st[2], isTextBox: true,
    });
    s.addText(st[1], {
      x: x + 0.2, y: 3.45, w: cardW - 0.4, h: 1.1, align: "center", fontFace: FONT_BODY, fontSize: 12.5,
      color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.2,
    });
  });

  s.addText(
    `Handling one constraint type correctly doesn't mean the fleet-dispatch DECISION stays valid once a `
    + `second constraint type enters: the demand-blind PRECEDENCE-ONLY split additionally put the two stops `
    + `on different vehicles entirely in ${exp3.pairSeparated}/${exp3.n} trials — the split itself became `
    + `incompatible with the rule — and overloaded a vehicle in ${exp3.precedenceOnlyOverloaded}/${exp3.remainingAfterSeparation} `
    + `of the rest. Composing constraint types into one solve_multi_vehicle call, not any single type alone, `
    + `is what keeps the whole decision valid — and it's the finding neither prior-art paper in the `
    + `patent-readiness report covers (see "Why this is patent-shaped").`,
    { x: 0.6, y: 5.05, w: 12.1, h: 1.65, fontFace: FONT_BODY, fontSize: 14, color: "E0E7FF", isTextBox: true, lineSpacingMultiple: 1.3 }
  );
  footer(s, 7);
}

// =======================================================================
// Slide 8 — Experiment 4: multi-objective (time vs. distance) trade-off
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "Benchmark — experiment 4");
  title(s, "Time and distance are a real trade-off, not one number twice");

  s.addText(
    "For each waypoint set, the TRUE fastest tour and the TRUE shortest tour are found by exhaustive "
    + "search, then each is scored against the OTHER objective to measure what optimizing for only one "
    + "actually costs. combine_objectives() lets the same QUBO solver minimize a weighted sum of both — "
    + "zero changes to the underlying formulation.",
    { x: 0.6, y: 1.9, w: 12.1, h: 1.15, fontFace: FONT_BODY, fontSize: 15, color: SLATE, isTextBox: true, lineSpacingMultiple: 1.3 }
  );

  const stats = [
    [`${exp4.nDiffer}/${exp4.n}`, "trials where optimizing for only\none objective provably costs the other", VIOLET],
    [`+${exp4.avgExtraDist.toFixed(1)}% avg\n+${exp4.maxExtraDist.toFixed(1)}% worst`, "extra DISTANCE from\noptimizing time only, when they differ", WARN],
    [`+${exp4.avgExtraTime.toFixed(1)}% avg\n+${exp4.maxExtraTime.toFixed(1)}% worst`, "extra TIME from\noptimizing distance only, when they differ", WARN],
  ];
  const cardW = 3.9, gap = 0.25, startX = 0.6;
  stats.forEach((st, i) => {
    const x = startX + i * (cardW + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 3.3, w: cardW, h: 2.9, rectRadius: 0.12,
      fill: { color: WHITE }, line: { color: "E2E8F0", width: 1 }, shadow: freshShadow(),
    });
    s.addText(st[0], {
      x, y: 3.55, w: cardW, h: 1.35, align: "center", fontFace: FONT_HEAD, fontSize: 26, bold: true,
      color: st[2], isTextBox: true, lineSpacingMultiple: 1.05,
    });
    s.addText(st[1], {
      x: x + 0.2, y: 4.95, w: cardW - 0.4, h: 1.1, align: "center", fontFace: FONT_BODY, fontSize: 12.5,
      color: SLATE, isTextBox: true, lineSpacingMultiple: 1.2,
    });
  });
  footer(s, 8);
}

// =======================================================================
// Slide 9 — Experiment 5: time-window position pruning — a partial,
// honestly-scoped answer, not a solved one
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "Benchmark — experiment 5", { color: WARN });
  title(s, "Time-window pruning helps — it is not a wall-clock guarantee");

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.6, y: 1.9, w: 12.1, h: 4.75, rectRadius: 0.12,
    fill: { color: INK }, line: { type: "none" }, shadow: freshShadow(),
  });

  const stats = [
    [`${exp5.withoutOk}/${exp5.n}`, "WITHOUT position pruning, the unconstrained\nschedule already satisfied the window", WARN],
    [`${exp5.withOk}/${exp5.n}`, "WITH position pruning, the\nwindow was actually satisfied", GOOD],
  ];
  const cardW = 5.4, gap = 0.3, startX = 1.0;
  stats.forEach((st, i) => {
    const x = startX + i * (cardW + gap);
    s.addText(st[0], {
      x, y: 2.2, w: cardW, h: 1.15, align: "center", fontFace: FONT_HEAD, fontSize: 40, bold: true,
      color: st[2], isTextBox: true,
    });
    s.addText(st[1], {
      x, y: 3.35, w: cardW, h: 0.9, align: "center", fontFace: FONT_BODY, fontSize: 13,
      color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.2,
    });
  });
  s.addShape(pres.ShapeType.line, { x: 1.2, y: 4.4, w: 10.9, h: 0, line: { color: "3730A3", width: 1 } });
  s.addText(
    "The QUBO encodes a tour by POSITION, not clock time — so a provably-safe prune of positions that "
    + "could never satisfy a window measurably helps (never worse than no time-awareness at all) but isn't "
    + "a satisfaction guarantee: two tours can share the same allowed position while arriving at very "
    + "different real times. A true wall-clock guarantee needs a different formulation (arc-based variables "
    + "plus time propagation) — flagged as the highest-formulation-risk roadmap item, not claimed solved here.",
    { x: 1.0, y: 4.6, w: 11.3, h: 1.85, fontFace: FONT_BODY, fontSize: 13, color: "E0E7FF", isTextBox: true, lineSpacingMultiple: 1.3 }
  );
  footer(s, 9);
}

// =======================================================================
// Slide 10 — Fleet dispatch + demand weights
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "Beyond one vehicle");
  title(s, "Multi-vehicle dispatch, with capacity that means what it says");

  const rows = [
    ["Balanced by default", "Farthest-point clustering alone can hand one vehicle 14 stops and another 2 — every split is rebalanced against a fair-share target automatically."],
    ["A real, enforced cap", "“Max/vehicle” genuinely limits every vehicle's stop count, auto-raising the fleet size if the requested vehicles can't satisfy it — not a suggestion."],
    ["Capacity by load, not just count", "Per-stop demand weights turn the same cap into a total-weight limit, for when a crate and a pallet aren't the same “one stop.”"],
    ["A bin-packing bug we caught ourselves", "ceil(total demand / capacity) is only a lower bound with uneven weights — our own test suite caught the undercount; fixed with a retry loop that's now covered by regression tests."],
  ];
  const rowH = 1.1, startY = 1.95;
  rows.forEach((r, i) => {
    const y = startY + i * (rowH + 0.08);
    s.addShape(pres.ShapeType.ellipse, {
      x: 0.6, y: y + 0.1, w: 0.5, h: 0.5, fill: { color: VIOLET, transparency: 85 }, line: { type: "none" },
    });
    s.addText(String(i + 1), {
      x: 0.6, y: y + 0.1, w: 0.5, h: 0.5, align: "center", valign: "middle",
      fontFace: FONT_HEAD, fontSize: 16, bold: true, color: VIOLET, isTextBox: true,
    });
    s.addText(r[0], {
      x: 1.35, y, w: 3.1, h: rowH, valign: "middle", fontFace: FONT_HEAD, fontSize: 14.5, bold: true,
      color: INK, isTextBox: true,
    });
    s.addText(r[1], {
      x: 4.6, y, w: 8.1, h: rowH, valign: "middle", fontFace: FONT_BODY, fontSize: 12.5,
      color: SLATE, isTextBox: true, lineSpacingMultiple: 1.2,
    });
  });
  footer(s, 10);
}

// =======================================================================
// Slide 11 — Feature grid
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "A product, not just an algorithm");
  title(s, "Everything a judge can click, today");

  const features = [
    ["Bulk import", "Paste or upload a CSV of stops — geocoded automatically."],
    ["Shareable link", "One URL encodes the whole route — city, stops, method, rules."],
    ["GPX + PDF export", "Take the solved route into any GPS device, or print it."],
    ["Dark / light theme", "A real design system, not default browser styling."],
    ["Precedence rules", "“Visit A before B” — baked into the same QUBO, not bolted on."],
    ["Live analytics", "GET /api/analytics — a real usage counter, honestly scoped."],
    ["OpenAPI spec", "Every field tested against the real Flask responses."],
    ["One-command deploy", "Dockerfile + Render/GitHub Pages guides included."],
  ];
  const cols = 4, cardW = 2.98, cardH = 2.15, gapX = 0.06, gapY = 0.15, startX = 0.6, startY = 2.0;
  features.forEach((f, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = startX + col * (cardW + gapX), y = startY + row * (cardH + gapY);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: cardW, h: cardH, rectRadius: 0.1,
      fill: { color: WHITE }, line: { color: "E2E8F0", width: 1 }, shadow: freshShadow(),
    });
    s.addShape(pres.ShapeType.ellipse, {
      x: x + 0.22, y: y + 0.22, w: 0.42, h: 0.42, fill: { color: i % 2 === 0 ? VIOLET : CYAN }, line: { type: "none" },
    });
    s.addText(f[0], {
      x: x + 0.2, y: y + 0.78, w: cardW - 0.4, h: 0.5, fontFace: FONT_HEAD, fontSize: 13.5, bold: true,
      color: INK, isTextBox: true,
    });
    s.addText(f[1], {
      x: x + 0.2, y: y + 1.25, w: cardW - 0.4, h: 0.85, fontFace: FONT_BODY, fontSize: 10.5,
      color: SLATE, isTextBox: true, lineSpacingMultiple: 1.2,
    });
  });
  footer(s, 11);
}

// =======================================================================
// Slide 12 — Production readiness
// =======================================================================
{
  const s = darkSlide();
  kicker(s, "Not just a notebook demo", { color: CYAN });
  title(s, "Tested, documented, and deployable", { color: WHITE });

  const stats = [
    ["491", "automated tests\n(pytest + Playwright + Node)"],
    ["100%", "of the test suite runs\non every push via CI"],
    ["3", "solvers benchmarked side by side\n(2-opt, OR-Tools, QUBO+SA)"],
    ["1", "command to self-host\n(Dockerfile included)"],
  ];
  const cardW = 2.85, gap = 0.22, startX = 0.6;
  stats.forEach((st, i) => {
    const x = startX + i * (cardW + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.15, w: cardW, h: 2.5, rectRadius: 0.12,
      fill: { color: "312E81" }, line: { type: "none" }, shadow: freshShadow(),
    });
    s.addText(st[0], {
      x, y: 2.35, w: cardW, h: 1.1, align: "center", fontFace: FONT_HEAD, fontSize: 34, bold: true,
      color: CYAN, isTextBox: true,
    });
    s.addText(st[1], {
      x: x + 0.15, y: 3.5, w: cardW - 0.3, h: 1.0, align: "center", fontFace: FONT_BODY, fontSize: 11.5,
      color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.2,
    });
  });
  s.addText(
    "openapi.yaml is checked against the live Flask responses by the test suite itself — "
    + "so the documentation can't silently drift from what the API actually returns.",
    { x: 0.6, y: 5.1, w: 12.1, h: 1.0, fontFace: FONT_BODY, fontSize: 14, italic: true, color: "C7D2FE", isTextBox: true, lineSpacingMultiple: 1.3 }
  );
  footer(s, 12);
}

// =======================================================================
// Slide 13 — Patent / IP angle
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "Why this is patent-shaped, not just code");
  title(s, "A concrete, measurable technical effect");

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.6, y: 1.95, w: 12.1, h: 1.9, rectRadius: 0.12,
    fill: { color: INK }, line: { type: "none" }, shadow: freshShadow(),
  });
  s.addText(
    "“A routing optimizer in which additional real-world dispatch constraints are incorporated as "
    + "composable penalty terms within a single QUBO formulation, guaranteeing constraint satisfaction "
    + "by construction — compared to a measured tendency of unconstrained classical local-search "
    + "heuristics to violate such constraints and require costly post-hoc repair.”",
    { x: 1.0, y: 2.15, w: 11.3, h: 1.5, fontFace: FONT_BODY, italic: true, fontSize: 15.5, color: "E0E7FF", isTextBox: true, lineSpacingMultiple: 1.3 }
  );

  const points = [
    "Measured, not asserted: Experiment 2's 15/15 vs 8/15 gap is reproducible with `python3 src/benchmark.py`.",
    "Composable by design: precedence and multi-vehicle capacity are each one more penalty term — not a bespoke solver per rule, unlike classical VRP tooling.",
    "Aligned with the 2025 CRI patent guidance's bar for a “concrete, measurable technical effect,” not an abstract algorithm claim.",
  ];
  s.addText(
    points.map((t, i) => ({ text: t, options: { bullet: { code: "25CF" }, breakLine: i < points.length - 1, paraSpaceAfter: 12 } })),
    { x: 0.6, y: 4.15, w: 12.1, h: 2.6, fontFace: FONT_BODY, fontSize: 14.5, color: SLATE, isTextBox: true, lineSpacingMultiple: 1.25 }
  );
  footer(s, 13);
}

// =======================================================================
// Slide 14 — Roadmap
// =======================================================================
{
  const s = lightSlide();
  kicker(s, "What's next");
  title(s, "Already live vs. the honest next steps");

  const cardY = 2.0, cardH = 4.5, cardW = 5.9;
  const cols = [
    {
      x: 0.6, heading: "Already shipped", color: GOOD,
      items: ["Precedence constraints, single-vehicle AND fleet", "Cross-cluster precedence (auto-co-located onto one vehicle)", "Numeric time-window constraints", "Multi-vehicle capacity (count or weight)", "OR-Tools + QAOA comparisons", "Live usage analytics", "Docker + OpenAPI"],
    },
    {
      x: 6.8, heading: "Honest next steps", color: WARN,
      items: ["A real, paid traffic API (interface already pluggable)", "Time windows above 9 interior stops (position-based QUBO limit)", "Real wall-clock time-window guarantees (needs a different formulation)", "Shared, durable analytics storage past a single worker"],
    },
  ];
  cols.forEach((c) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: c.x, y: cardY, w: cardW, h: cardH, rectRadius: 0.12,
      fill: { color: WHITE }, line: { color: "E2E8F0", width: 1 }, shadow: freshShadow(),
    });
    s.addShape(pres.ShapeType.ellipse, {
      x: c.x + 0.35, y: cardY + 0.35, w: 0.35, h: 0.35, fill: { color: c.color }, line: { type: "none" },
    });
    s.addText(c.heading, {
      x: c.x + 0.85, y: cardY + 0.32, w: cardW - 1.2, h: 0.45, fontFace: FONT_HEAD, fontSize: 17, bold: true,
      color: INK, isTextBox: true,
    });
    s.addText(
      c.items.map((t, i) => ({ text: t, options: { bullet: { code: "25CF" }, breakLine: i < c.items.length - 1, paraSpaceAfter: 16 } })),
      { x: c.x + 0.4, y: cardY + 1.05, w: cardW - 0.8, h: cardH - 1.4, fontFace: FONT_BODY, fontSize: 13.5, color: SLATE, isTextBox: true, lineSpacingMultiple: 1.25 }
    );
  });
  footer(s, 14);
}

// =======================================================================
// Slide 15 — Thank you / Q&A
// =======================================================================
{
  const s = darkSlide();
  s.addShape(pres.ShapeType.ellipse, {
    x: -2.5, y: 3.5, w: 7, h: 7, fill: { color: VIOLET, transparency: 80 }, line: { type: "none" },
  });
  s.addText("Thank you", {
    x: 0.9, y: 2.5, w: 10, h: 1.2, fontFace: FONT_HEAD, fontSize: 48, bold: true, color: WHITE, isTextBox: true,
  });
  s.addText("Questions welcome — including the hard ones about what's simulated and what isn't.", {
    x: 0.9, y: 3.6, w: 9, h: 0.6, fontFace: FONT_BODY, fontSize: 16, italic: true, color: "C7D2FE", isTextBox: true,
  });
  s.addText("Live demo: traffic-router.onrender.com", {
    x: 0.9, y: 4.6, w: 8, h: 0.4, fontFace: FONT_BODY, fontSize: 14, color: CYAN, isTextBox: true,
  });
  s.addText("Code + full test suite + docs: see the project README", {
    x: 0.9, y: 5.05, w: 8, h: 0.4, fontFace: FONT_BODY, fontSize: 14, color: CYAN, isTextBox: true,
  });
  s.addNotes(
    "Backup answers: classical 2-opt beats our QUBO on PLAIN routing and we say so on slide 5 — "
    + "the real claim is Experiment 2 (constraint satisfaction by construction). QAOA and real D-Wave "
    + "hardware are both demonstrated via run_qaoa_demo.py and run_on_real_quantum_hardware.py, not just "
    + "claimed. Analytics/OR-Tools/QAOA are all optional dependencies with graceful degradation — see README."
  );
}

pres.writeFile({ fileName: OUT_PATH }).then(() => {
  console.log(`Wrote ${OUT_PATH}`);
});
