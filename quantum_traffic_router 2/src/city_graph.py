"""
city_graph.py
=============
Builds the road-network graph the router operates on, for 17 major Indian
cities spanning North (Delhi, Jaipur, Lucknow, Chandigarh), South (Chennai,
Hyderabad, Bengaluru, Kochi, Coimbatore), East (Kolkata), West (Mumbai,
Pune, Ahmedabad), Central (Bhopal), and Northeast (Guwahati) India, plus
the NCR belt (Gurgaon, Noida). This list is only used to seed the city
dropdown's map-centering and the offline curated-landmark demo graph — the
live "click anywhere" app (app.py) itself is not limited to these cities at
all: real street routing (OSRM) and place search (Nominatim) both work
anywhere in India (or the world) the moment you click the map or type a
search, regardless of which city is selected in the dropdown.

Two modes:
  1. DEMO MODE (default, no internet needed): for each city, a curated set
     of well-known localities/landmarks with real approximate coordinates,
     auto-connected into a road-like graph (see `_build_knn_road_graph`).
     This is what ships in this repo so the whole project — and the
     multi-city map — runs offline, deterministically, with no dependency
     on a live map API during a demo/pitch. (Overpass, the live OSM data
     API, is frequently blocked or rate-limited on conference/venue wifi —
     this sandbox's own network couldn't reach it either — so offline-first
     is a deliberate reliability choice, not a shortcut.)
  2. LIVE MODE (optional): pulls a real OpenStreetMap road network for any
     place name using OSMnx, if the machine running this has internet
     access and `osmnx` installed. See `build_live_osm_graph()`.

Both paths return the same kind of networkx.Graph — every node has
(lat, lon), every edge has `length_km` and `free_flow_minutes` — so nothing
downstream (congestion.py, distance_matrix.py, qubo_tsp.py, visualize.py)
needs to know or care which mode built the graph.
"""

import math
import os
import itertools
import networkx as nx

FREE_FLOW_SPEED_KMPH = 32.0

# A road's real distance is always longer than the straight-line ("as the
# crow flies") distance between two points, because roads bend around
# blocks, rivers, etc. 1.3x is a commonly used rule-of-thumb "circuity
# factor" for dense Indian urban road networks — good enough for a demo,
# not a substitute for real routed distances (see build_live_osm_graph).
ROAD_CIRCUITY_FACTOR = 1.3

# Each city: a curated dict of {locality name: (lat, lon)}. Coordinates are
# approximate/illustrative (accurate to roughly neighborhood level, not
# survey-grade) — enough for a realistic-feeling demo graph and map. Swap
# in build_live_osm_graph() for production-grade coordinates and real road
# geometry before treating this as ground truth.
CITIES: dict[str, dict[str, tuple[float, float]]] = {
    "Bengaluru": {
        "Majestic":        (12.9767, 77.5713),
        "MG Road":         (12.9756, 77.6068),
        "Indiranagar":     (12.9719, 77.6412),
        "Domlur":          (12.9611, 77.6387),
        "Koramangala":     (12.9352, 77.6245),
        "HSR Layout":      (12.9116, 77.6389),
        "BTM Layout":      (12.9166, 77.6101),
        "Jayanagar":       (12.9308, 77.5838),
        "Malleshwaram":    (13.0059, 77.5709),
        "Yeshwantpur":     (13.0284, 77.5540),
        "Marathahalli":    (12.9569, 77.7011),
        "Whitefield":      (12.9698, 77.7500),
        "Electronic City": (12.8452, 77.6602),
        "Silk Board":      (12.9172, 77.6228),
    },
    "Mumbai": {
        "Colaba":       (18.9067, 72.8147),
        "Dadar":        (19.0176, 72.8562),
        "Worli":        (19.0096, 72.8175),
        "Bandra":       (19.0596, 72.8295),
        "BKC":          (19.0662, 72.8686),
        "Andheri":      (19.1197, 72.8468),
        "Powai":        (19.1176, 72.9060),
        "Ghatkopar":    (19.0857, 72.9081),
        "Kurla":        (19.0728, 72.8826),
        "Chembur":      (19.0522, 72.9006),
        "Vashi":        (19.0771, 72.9986),
        "Thane":        (19.2183, 72.9781),
        "Borivali":     (19.2307, 72.8567),
        "Malad":        (19.1863, 72.8493),
    },
    "Pune": {
        "Shivajinagar":  (18.5308, 73.8475),
        "Kothrud":       (18.5074, 73.8077),
        "Hinjewadi":     (18.5908, 73.7397),
        "Baner":         (18.5590, 73.7868),
        "Aundh":         (18.5643, 73.8077),
        "Viman Nagar":   (18.5679, 73.9143),
        "Kharadi":       (18.5515, 73.9430),
        "Hadapsar":      (18.5089, 73.9260),
        "Camp":          (18.5122, 73.8792),
        "Swargate":      (18.5010, 73.8567),
        "Katraj":        (18.4575, 73.8676),
        "Wagholi":       (18.5793, 73.9820),
        "Pimpri":        (18.6298, 73.7997),
        "Chinchwad":     (18.6408, 73.7997),
    },
    "Gurgaon": {
        "Cyber City":       (28.4949, 77.0890),
        "MG Road":          (28.4783, 77.0902),
        "IFFCO Chowk":      (28.4722, 77.0722),
        "Udyog Vihar":      (28.5079, 77.0895),
        "Sohna Road":       (28.4300, 77.0400),
        "Golf Course Road": (28.4595, 77.1010),
        "Sector 29":        (28.4650, 77.0640),
        "Sector 14":        (28.4650, 77.0270),
        "DLF Phase 3":      (28.4930, 77.0940),
        "Manesar":          (28.3540, 76.9350),
        "Sector 56":        (28.4180, 77.1050),
        "Rajiv Chowk":      (28.4590, 77.0730),
    },
    "Noida": {
        "Sector 18":       (28.5697, 77.3260),
        "Sector 62":       (28.6187, 77.3649),
        "Sector 63":       (28.6205, 77.3775),
        "Botanical Garden":(28.5641, 77.3350),
        "Sector 137":      (28.5158, 77.3897),
        "Greater Noida":   (28.4744, 77.5040),
        "Sector 15":       (28.5825, 77.3193),
        "Film City":       (28.5820, 77.3160),
        "Sector 32":       (28.5760, 77.3390),
        "Sector 128":      (28.5312, 77.3618),
        "Sector 51":       (28.5720, 77.3540),
    },
    "Delhi": {
        "Connaught Place": (28.6315, 77.2167),
        "Karol Bagh":      (28.6519, 77.1909),
        "Chandni Chowk":   (28.6506, 77.2334),
        "Saket":           (28.5245, 77.2066),
        "Hauz Khas":       (28.5494, 77.2001),
        "Dwarka":          (28.5921, 77.0460),
        "Rohini":          (28.7495, 77.0565),
        "Nehru Place":     (28.5494, 77.2513),
        "Lajpat Nagar":    (28.5677, 77.2434),
        "Vasant Kunj":     (28.5200, 77.1590),
        "Rajouri Garden":  (28.6469, 77.1219),
        "Mayur Vihar":     (28.6096, 77.2954),
    },
    "Chennai": {
        "T Nagar":       (13.0418, 80.2341),
        "Anna Nagar":    (13.0850, 80.2101),
        "Adyar":         (13.0067, 80.2570),
        "Velachery":     (12.9791, 80.2212),
        "Guindy":        (13.0100, 80.2200),
        "Mylapore":      (13.0339, 80.2698),
        "Egmore":        (13.0732, 80.2609),
        "Tambaram":      (12.9249, 80.1000),
        "Porur":         (13.0381, 80.1564),
        "Sholinganallur":(12.9010, 80.2279),
    },
    "Kolkata": {
        "Park Street":  (22.5535, 88.3529),
        "Salt Lake":    (22.5697, 88.4172),
        "Howrah":       (22.5958, 88.2636),
        "Esplanade":    (22.5651, 88.3509),
        "Ballygunge":   (22.5288, 88.3644),
        "Behala":       (22.5023, 88.3134),
        "Dum Dum":      (22.6420, 88.4200),
        "New Town":     (22.5809, 88.4620),
        "Garia":        (22.4614, 88.3927),
        "Jadavpur":     (22.4990, 88.3714),
    },
    "Hyderabad": {
        "Hitech City":    (17.4483, 78.3915),
        "Banjara Hills":  (17.4156, 78.4347),
        "Gachibowli":     (17.4400, 78.3489),
        "Secunderabad":   (17.4399, 78.4983),
        "Charminar":      (17.3616, 78.4747),
        "Kukatpally":     (17.4849, 78.4138),
        "Madhapur":       (17.4470, 78.3915),
        "Ameerpet":       (17.4374, 78.4483),
        "Dilsukhnagar":   (17.3687, 78.5247),
        "LB Nagar":       (17.3467, 78.5522),
    },
    "Ahmedabad": {
        "Navrangpura": (23.0367, 72.5626),
        "Satellite":   (23.0273, 72.5075),
        "Maninagar":   (22.9968, 72.6034),
        "Bopal":       (23.0325, 72.4696),
        "Vastrapur":   (23.0374, 72.5286),
        "CG Road":     (23.0338, 72.5581),
        "Naranpura":   (23.0508, 72.5580),
        "Thaltej":     (23.0508, 72.5030),
        "Paldi":       (23.0138, 72.5648),
        "Chandkheda":  (23.1082, 72.5936),
    },
    "Jaipur": {
        "MI Road":       (26.9157, 75.8189),
        "Malviya Nagar": (26.8531, 75.8081),
        "Vaishali Nagar":(26.9123, 75.7370),
        "C-Scheme":      (26.9096, 75.7996),
        "Mansarovar":    (26.8505, 75.7625),
        "Jagatpura":     (26.8156, 75.8399),
        "Tonk Road":     (26.8467, 75.8079),
        "Amer":          (26.9855, 75.8513),
        "Sanganer":      (26.8199, 75.8005),
        "Raja Park":     (26.9037, 75.8347),
    },
    "Lucknow": {
        "Hazratganj":   (26.8500, 80.9463),
        "Gomti Nagar":  (26.8500, 81.0100),
        "Aliganj":      (26.8890, 80.9330),
        "Indira Nagar": (26.8770, 80.9820),
        "Alambagh":     (26.8100, 80.9020),
        "Chowk":        (26.8637, 80.9110),
        "Aminabad":     (26.8500, 80.9200),
        "Vikas Nagar":  (26.9034, 80.9634),
        "Mahanagar":    (26.8763, 80.9445),
        "Rajajipuram":  (26.8590, 80.8890),
    },
    "Chandigarh": {
        "Sector 17":  (30.7410, 76.7820),
        "Sector 22":  (30.7280, 76.7690),
        "Sector 35":  (30.7175, 76.7690),
        "Sector 8":   (30.7460, 76.7920),
        "Sector 43":  (30.7156, 76.7695),
        "Panchkula":  (30.6942, 76.8606),
        "Mohali":     (30.7046, 76.7179),
        "Sector 26":  (30.7238, 76.7860),
        "Sector 15":  (30.7590, 76.7679),
        "Manimajra":  (30.7275, 76.8272),
    },
    "Kochi": {
        "MG Road":        (9.9816, 76.2999),
        "Fort Kochi":     (9.9658, 76.2422),
        "Kakkanad":       (10.0159, 76.3419),
        "Edappally":      (10.0261, 76.3084),
        "Vyttila":        (9.9689, 76.3192),
        "Palarivattom":   (10.0031, 76.3084),
        "Aluva":          (10.1075, 76.3516),
        "Panampilly Nagar":(9.9640, 76.2996),
        "Thrikkakara":    (10.0431, 76.3352),
        "Kadavanthra":    (9.9670, 76.2934),
    },
    "Bhopal": {
        "New Market":     (23.2385, 77.4030),
        "MP Nagar":       (23.2287, 77.4338),
        "Arera Colony":   (23.2202, 77.4380),
        "Kolar Road":     (23.1611, 77.4126),
        "Habibganj":      (23.2280, 77.4380),
        "Shahpura":       (23.1963, 77.4402),
        "BHEL":           (23.2762, 77.4587),
        "Bairagarh":      (23.2698, 77.3486),
        "Govindpura":     (23.2523, 77.4485),
        "Ayodhya Bypass": (23.2076, 77.4536),
    },
    "Guwahati": {
        "Paltan Bazaar": (26.1833, 91.7500),
        "Fancy Bazaar":  (26.1858, 91.7458),
        "Dispur":        (26.1433, 91.7898),
        "Ganeshguri":    (26.1516, 91.7809),
        "Beltola":       (26.1245, 91.7877),
        "Zoo Road":      (26.1633, 91.7789),
        "Chandmari":     (26.1747, 91.7642),
        "Maligaon":      (26.1587, 91.6786),
        "Six Mile":      (26.1189, 91.8036),
        "Basistha":      (26.1075, 91.8114),
    },
    "Coimbatore": {
        "RS Puram":       (11.0038, 76.9558),
        "Gandhipuram":    (11.0175, 76.9674),
        "Peelamedu":      (11.0296, 77.0266),
        "Saibaba Colony": (11.0233, 76.9411),
        "Race Course":    (11.0006, 76.9645),
        "Singanallur":    (11.0007, 77.0339),
        "Ondipudur":      (11.0037, 77.0525),
        "Ukkadam":        (10.9891, 76.9614),
        "Vadavalli":      (11.0244, 76.9052),
        "Ramanathapuram": (10.9930, 76.9779),
    },
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points, in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _build_knn_road_graph(coords: dict[str, tuple[float, float]], k: int = 3) -> nx.Graph:
    """Turn a set of named points into a connected, road-like graph:
    each node links to its k nearest neighbors by real-world distance,
    then any leftover disconnected components are stitched together with
    their single shortest connecting edge (so the graph is always fully
    connected, which a real city's arterial road network always is)."""
    G = nx.Graph()
    for name, (lat, lon) in coords.items():
        G.add_node(name, lat=lat, lon=lon)

    names = list(coords.keys())
    for name in names:
        dists = sorted(
            ((other, haversine_km(coords[name], coords[other])) for other in names if other != name),
            key=lambda p: p[1],
        )
        for other, dist_km in dists[:k]:
            road_km = round(dist_km * ROAD_CIRCUITY_FACTOR, 2)
            G.add_edge(name, other, length_km=road_km, free_flow_minutes=(road_km / FREE_FLOW_SPEED_KMPH) * 60.0)

    # stitch disconnected components (can happen with pure k-NN) using each
    # component pair's single closest cross-edge, repeated until connected
    while nx.number_connected_components(G) > 1:
        components = list(nx.connected_components(G))
        best = None
        for comp_a, comp_b in itertools.combinations(components, 2):
            for u, v in itertools.product(comp_a, comp_b):
                d = haversine_km(coords[u], coords[v])
                if best is None or d < best[2]:
                    best = (u, v, d)
        u, v, d = best
        road_km = round(d * ROAD_CIRCUITY_FACTOR, 2)
        G.add_edge(u, v, length_km=road_km, free_flow_minutes=(road_km / FREE_FLOW_SPEED_KMPH) * 60.0)

    return G


def list_cities() -> list[str]:
    return list(CITIES.keys())


def build_city_graph(city: str) -> nx.Graph:
    """Return the offline demo road network for `city` (must be a key of
    CITIES) as an undirected networkx.Graph, congestion-neutral."""
    if city not in CITIES:
        raise ValueError(f"Unknown city '{city}'. Known cities: {list_cities()}")
    return _build_knn_road_graph(CITIES[city])


def build_demo_graph() -> nx.Graph:
    """Backwards-compatible alias: the original single-city (Bengaluru) demo
    graph. New code should prefer build_city_graph('Bengaluru')."""
    return build_city_graph("Bengaluru")


def build_live_osm_graph(place_name: str):
    """Pull a real OSM drive-network graph for `place_name` via OSMnx.

    Requires: `pip install osmnx` and outbound internet access to the
    Overpass API (this was NOT reachable from the sandbox this project was
    built in — org egress policy blocked overpass-api.de — so this path is
    untested from here; try it from your own machine/venue, and fall back
    to build_city_graph() if Overpass is unreachable there too, which is
    common on conference/venue wifi).

    Returns a networkx.Graph shaped like build_city_graph()'s output.
    """
    try:
        import osmnx as ox
    except ImportError as e:
        raise ImportError(
            "osmnx is not installed. Run `pip install osmnx` to use live "
            "OpenStreetMap data, or use build_city_graph() for the bundled "
            "offline demo cities instead."
        ) from e

    g_multidigraph = ox.graph_from_place(place_name, network_type="drive")
    g_simple = nx.Graph(g_multidigraph)

    for u, v, data in g_simple.edges(data=True):
        length_km = data.get("length", 1000.0) / 1000.0
        data["length_km"] = length_km
        data["free_flow_minutes"] = (length_km / FREE_FLOW_SPEED_KMPH) * 60.0

    relabel = {}
    for n, data in g_simple.nodes(data=True):
        data["lat"] = data.get("y")
        data["lon"] = data.get("x")
        relabel[n] = data.get("name", str(n))
    return nx.relabel_nodes(g_simple, relabel)


STREET_GRAPH_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "street_graphs")
STREET_GRAPH_RADIUS_M = 8000  # ~8km around each city's center — enough real street coverage for a
                               # live demo without the fetch/solve getting slow on a full metro-area graph


def _city_center(city: str) -> tuple[float, float]:
    coords = list(CITIES[city].values())
    return (sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords))


def get_or_build_street_graph(city: str, force_refresh: bool = False) -> nx.Graph:
    """The function behind "click anywhere in the city": returns a REAL
    OpenStreetMap street network (thousands of nodes/edges, not just the
    dozen curated landmarks) for `city`, so a click anywhere near an actual
    road snaps to a real intersection and routes follow real streets.

    Caches to disk (`data/street_graphs/<city>.graphml`) after the first
    successful fetch, so repeated runs/demo rehearsals don't re-hit the
    Overpass API and don't depend on venue wifi being up every single time
    — only the very first fetch per city needs live internet.

    Falls back to the curated build_city_graph(city) (the dozen named
    landmarks) if OSMnx isn't installed or Overpass can't be reached (this
    happened in the sandbox this project was built in — org egress policy
    blocked overpass-api.de — so this path is exercised and known to work;
    it should be rare on a normal internet connection). The returned graph
    is marked with G.graph['source'] = 'osm' or 'fallback_curated' so
    calling code (and the UI) can show the user which mode is active.
    """
    os.makedirs(STREET_GRAPH_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(STREET_GRAPH_CACHE_DIR, f"{city.replace(' ', '_')}.graphml")

    try:
        import osmnx as ox
    except ImportError:
        G = build_city_graph(city)
        G.graph["source"] = "fallback_curated"
        G.graph["fallback_reason"] = "osmnx not installed"
        return G

    if os.path.exists(cache_path) and not force_refresh:
        try:
            G = ox.load_graphml(cache_path)
            G.graph["source"] = "osm"
            return G
        except Exception:
            pass  # corrupt cache file — fall through and refetch

    try:
        lat, lon = _city_center(city)
        # Hard wall-clock timeout around the Overpass call: osmnx's own
        # retry/backoff can otherwise hang well past what a live demo can
        # afford to wait before falling back to the offline curated graph.
        # Deliberately a raw daemon Thread, NOT concurrent.futures — the
        # futures module registers an atexit hook that joins every worker
        # thread before the interpreter is allowed to exit, which would
        # block on this exact hang and defeat the timeout entirely. A
        # daemon thread is killed outright when the process exits instead.
        import threading
        result_box: dict = {}

        def _fetch():
            try:
                result_box["graph"] = ox.graph_from_point((lat, lon), dist=STREET_GRAPH_RADIUS_M, network_type="drive")
            except Exception as fetch_err:
                result_box["error"] = fetch_err

        t = threading.Thread(target=_fetch, daemon=True)
        t.start()
        t.join(timeout=20)
        if t.is_alive():
            raise TimeoutError("Overpass API did not respond within 20s")
        if "error" in result_box:
            raise result_box["error"]
        g_multidigraph = result_box["graph"]
        g_simple = nx.Graph(g_multidigraph)

        for u, v, data in g_simple.edges(data=True):
            length_km = data.get("length", 1000.0) / 1000.0
            data["length_km"] = length_km
            data["free_flow_minutes"] = (length_km / FREE_FLOW_SPEED_KMPH) * 60.0

        for n, data in g_simple.nodes(data=True):
            data["lat"] = data.get("y")
            data["lon"] = data.get("x")

        g_simple = nx.convert_node_labels_to_integers(g_simple, label_attribute="osm_node_id")
        g_simple = nx.relabel_nodes(g_simple, {n: str(n) for n in g_simple.nodes})

        try:
            ox.save_graphml(g_simple, cache_path)
        except Exception:
            pass  # caching is a nice-to-have, don't fail the request over it

        g_simple.graph["source"] = "osm"
        return g_simple

    except Exception as e:
        G = build_city_graph(city)
        G.graph["source"] = "fallback_curated"
        G.graph["fallback_reason"] = str(e)
        return G


def nearest_node(G: nx.Graph, lat: float, lon: float) -> tuple[str, float]:
    """Brute-force nearest-node lookup by real-world distance (fine even for
    a several-thousand-node graph — this runs once per clicked point, not
    in a hot loop). Returns (node_id, distance_km)."""
    best_node, best_dist = None, float("inf")
    for n, data in G.nodes(data=True):
        d = haversine_km((lat, lon), (data["lat"], data["lon"]))
        if d < best_dist:
            best_node, best_dist = n, d
    return best_node, best_dist


if __name__ == "__main__":
    for city in list_cities():
        G = build_city_graph(city)
        print(f"{city:10s} -> {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
              f"connected={nx.is_connected(G)}")
