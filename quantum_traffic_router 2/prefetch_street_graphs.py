#!/usr/bin/env python3
"""
prefetch_street_graphs.py — run this ONCE from your own machine's normal
internet connection (NOT from inside a locked-down cloud sandbox or a
host whose IPs get rate-limited) to download real OpenStreetMap street
data for all 5 cities and save it into data/street_graphs/*.graphml.

WHY THIS MATTERS: cloud hosts like Render often can't reach the public
Overpass API (OpenStreetMap's live data service) at all — its operators
rate-limit or block traffic from cloud-provider/datacenter IP ranges to
protect the service from bots. That's exactly why a deployed app.py can
fall back to the curated dozen-landmark network even though the same code
works fine on a laptop. And Render's free tier resets its disk on every
redeploy anyway, so even a *successful* live fetch wouldn't stick around.

The fix: fetch the data once from a normal residential/office connection,
then commit the resulting .graphml files straight into the git repo. From
then on, every deploy (Render or anywhere else) already has real street
data sitting on disk and never needs to call Overpass at all — "click
anywhere in the city" gets proper street-following routes, reliably.

Usage:
    pip install -r requirements.txt      # if you haven't already
    python3 prefetch_street_graphs.py

Then commit what it downloaded:
    git add data/street_graphs/*.graphml
    git commit -m "Bundle pre-fetched real street data for all cities"
    git push

This takes a few minutes total (each city is an ~8km-radius street-network
download) and only needs to be redone if you add a new city later.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from city_graph import list_cities, get_or_build_street_graph  # noqa: E402


def main():
    cities = list_cities()
    print(f"Fetching real OpenStreetMap street data for: {', '.join(cities)}\n")

    results = {}
    for city in cities:
        print(f"--- {city} ---")
        try:
            G = get_or_build_street_graph(city, force_refresh=True)
            source = G.graph.get("source", "unknown")
            results[city] = source
            if source == "osm":
                print(f"  OK — {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
                      f"saved to data/street_graphs/{city}.graphml\n")
            else:
                reason = G.graph.get("fallback_reason", "unknown reason")
                print(f"  FAILED to reach OpenStreetMap ({reason}) — still using the curated "
                      f"fallback for {city}. Check your internet connection and rerun.\n")
        except Exception as e:
            results[city] = "error"
            print(f"  ERROR: {e}\n")

    ok = [c for c, s in results.items() if s == "osm"]
    bad = [c for c, s in results.items() if s != "osm"]
    print("=== Summary ===")
    print(f"Real street data cached for: {', '.join(ok) if ok else '(none)'}")
    if bad:
        print(f"Still on fallback for: {', '.join(bad)} — rerun this script for just those "
              f"cities once your connection is working, then commit the new .graphml files.")
    else:
        print("All cities done. Now run:\n"
              "  git add data/street_graphs/*.graphml\n"
              "  git commit -m \"Bundle pre-fetched real street data for all cities\"\n"
              "  git push")


if __name__ == "__main__":
    main()
