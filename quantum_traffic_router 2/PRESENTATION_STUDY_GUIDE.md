# Quantum-Inspired Traffic Router — Study Guide

## The one-line pitch (memorize this)

"We built a tool that figures out the smartest order to visit a list of stops — like a delivery van's daily route — using a quantum-inspired algorithm, and it accounts for real traffic changing throughout the day."

## What problem are we solving?

Imagine a delivery driver with 10 stops to make. There are thousands of possible orders to visit them in, and picking a bad one wastes fuel and time. This is called the "Traveling Salesman Problem" — a famous, genuinely hard computer science problem. Our app solves exactly this, but adds a real-world twist: traffic isn't the same all day, so the best order at 9am might not be the best order at 6pm.

## The pipeline, in plain steps

Think of it as a five-step assembly line, from map to final route.

**Step 1 — Get the map.** The app has road data for a city (with a live map you can click anywhere on in the browser demo). This is just "how far is it from point A to point B."

**Step 2 — Add traffic.** A road that takes 5 minutes at midnight might take 20 minutes at 6pm. The app has a traffic model that stretches travel times depending on the hour you pick. It can also simulate an accident — spike one road's time way up — to test whether the app can react.

**Step 3 — Build a mini travel-time table.** Once you've picked your stops (say, 8 of them), the app doesn't need the whole city map anymore — just one small table: "stop A to stop B takes this long," for every pair. This is called the distance matrix.

**Step 4 — Solve it (the "quantum-inspired" part).** This is the core idea. Instead of checking every possible order one by one (which becomes impossible as stops increase), the app reformats the problem into something called a QUBO — a mathematical format specifically designed for quantum computers and quantum-style algorithms. It then solves this QUBO using an algorithm inspired by "quantum annealing" (the technique real quantum computers use), but it runs on a normal computer. That's the "quantum-inspired" name: same problem-solving style as a quantum computer, no actual quantum hardware needed to demo it. Right now, this uses a simulated version — but the same code can be pointed at a real D-Wave quantum computer with one setting changed.

**Step 5 — Prove it's actually better.** The app also solves the same problem with a simple classical method (always go to the nearest unvisited stop next). It shows both routes side by side on the map, with a percentage showing how much time the quantum-inspired route saves.

**Extra features on top:** if there are too many stops for one solve, it automatically splits them into smaller nearby groups; if there's more than one vehicle, it splits the stops across vehicles (optionally capping how many stops one vehicle can carry); and if a road gets blocked mid-route, you can flag it and the app instantly re-solves the rest of the trip around it.

## How is this different from Google Maps?

This is the question judges will most likely ask — know this cold.

Google Maps answers "what's the fastest way from point A to point B." Our app answers a different question: "I have MANY stops — what ORDER should I visit them in?" That's a much harder combinatorial problem, and it's the real problem delivery companies and service fleets face every day.

The bigger difference is *how* it solves that problem: Google Maps uses classical, hidden algorithms. Our app uses a quantum-inspired approach — the same style of math real quantum computers use for hard problems like this. As quantum hardware improves, this exact approach could be run on real quantum computers to solve much bigger routing problems than classical computers can handle well. That's the whole point of the hackathon problem statement: preparing routing systems for the quantum era.

Be honest about limits if asked: our traffic is simulated (a time-of-day math model), not live GPS data from millions of phones like Google has, and we don't have voice navigation or public transit — this is a focused proof-of-concept of the optimization idea, not a full consumer navigation app.

## Key terms — simple definitions

**TSP (Traveling Salesman Problem):** the classic "what's the best order to visit a list of places" problem. Famous because it gets extremely hard to solve perfectly as the number of places grows.

**QUBO:** short for "Quadratic Unconstrained Binary Optimization." It's just a specific mathematical format for describing "which combination of yes/no choices gives the lowest total cost." Quantum computers and quantum-style algorithms are built to solve problems in this exact format.

**Quantum annealing:** a technique (used by real quantum computers like D-Wave's) for finding a low-cost solution by letting a system settle into a low-energy state, similar to how a shaken box of marbles settles into its lowest position. Our "quantum-inspired" algorithm mimics this process on a regular computer.

**Congestion model:** the math that adjusts travel times based on time of day, simulating rush hour vs. quiet hours.

**Clustering:** splitting a big list of stops into smaller nearby groups so each group can be solved on its own — this is how the app handles more stops than one solve can manage at once.

**Multi-vehicle dispatch:** splitting stops across more than one vehicle, each getting its own optimized loop starting and ending at a shared depot.

## Likely questions and simple answers

**"Is this using a real quantum computer?"**
Not in the live demo — it uses an algorithm inspired by quantum computing, run on a normal computer. It's designed so the exact same problem can be sent to a real quantum computer (like D-Wave's) with a small code change; we have a separate script ready to do that.

**"Why does this matter if it's not real quantum hardware yet?"**
Because the hard part is reformulating routing problems into a form quantum computers can actually solve (the QUBO). We've already done that work — this project is "quantum-ready," so it's positioned to benefit the moment quantum hardware becomes practical and accessible at scale.

**"What happens with 100 stops instead of 8?"**
The app automatically clusters them into smaller manageable groups rather than trying to solve one giant problem at once, so it still works — the quality gets slightly less "perfect" at huge scale, which we're upfront about.

**"Does it use real traffic data?"**
Not live GPS traffic — it uses a mathematical model that simulates typical time-of-day congestion patterns. This keeps the demo fully working without needing a live internet traffic API.

**"What's the actual output/result?"**
An optimized visiting order for all your stops, drawn on a live map, plus a clear percentage showing how much time you save compared to visiting them in the order you originally clicked them.

## If you only remember three things

1. It solves "what order should I visit these stops in," not "how do I get from A to B" — that's the real, different problem.
2. It uses a quantum-inspired algorithm (QUBO + simulated annealing), built so it can run on real quantum hardware later with minimal changes.
3. It proves its value by showing the optimized route next to the naive route with a visible time-savings percentage — nothing is a black box.
