"""Tests for src/city_graph.py — specifically the pan-India city coverage
(18 curated cities spanning North/South/East/West/Central/Northeast India)
added so the city dropdown isn't limited to a handful of NCR-adjacent
cities. The live click-anywhere app itself was never limited to these
cities (OSRM + Nominatim work anywhere), but the dropdown's map-centering
and the offline curated-landmark demo graph are, so this locks in that
every listed city actually has usable data behind it."""

import networkx as nx
import pytest

from city_graph import CITIES, _city_center, build_city_graph, list_cities

EXPECTED_MIN_CITIES = 18


def test_at_least_seventeen_cities_are_available():
    """The pan-India expansion added 13 cities on top of the original 5
    (Bengaluru, Mumbai, Pune, Gurgaon, Noida) — this is a floor, not an
    exact count, so future additions don't need to touch this test."""
    assert len(list_cities()) >= EXPECTED_MIN_CITIES


@pytest.mark.parametrize("city", [
    "Bengaluru", "Mumbai", "Pune", "Gurgaon", "Noida", "Delhi", "Chennai",
    "Kolkata", "Hyderabad", "Ahmedabad", "Jaipur", "Lucknow", "Chandigarh",
    "Kochi", "Bhopal", "Guwahati", "Coimbatore", "Nagpur",
])
def test_every_expected_city_is_registered(city):
    assert city in CITIES


@pytest.mark.parametrize("city", list(CITIES.keys()))
def test_every_city_has_enough_landmarks_and_valid_coordinates(city):
    """Each city needs enough named localities to make a non-trivial demo
    route, and every coordinate must be a real, plausible lat/lon inside
    India's bounding box (roughly 6-36 N, 68-98 E) — catches a obviously
    wrong/typo'd coordinate (e.g. swapped lat/lon) at test time rather than
    a silently broken pin on the map."""
    landmarks = CITIES[city]
    assert len(landmarks) >= 8, f"{city} has too few landmarks for a real demo route"
    for name, (lat, lon) in landmarks.items():
        assert 6.0 <= lat <= 36.0, f"{city} / {name} has an implausible latitude: {lat}"
        assert 68.0 <= lon <= 98.0, f"{city} / {name} has an implausible longitude: {lon}"


@pytest.mark.parametrize("city", list(CITIES.keys()))
def test_every_city_graph_is_fully_connected(city):
    """A real city's arterial road network is always fully connected —
    the k-NN + stitching construction in _build_knn_road_graph guarantees
    this, but it's worth locking in directly for every city, not just the
    original 5."""
    G = build_city_graph(city)
    assert nx.is_connected(G)
    assert G.number_of_nodes() == len(CITIES[city])


@pytest.mark.parametrize("city", list(CITIES.keys()))
def test_city_center_is_the_average_of_its_landmarks(city):
    lat, lon = _city_center(city)
    coords = list(CITIES[city].values())
    assert lat == pytest.approx(sum(c[0] for c in coords) / len(coords))
    assert lon == pytest.approx(sum(c[1] for c in coords) / len(coords))


def test_unknown_city_raises_a_clear_error():
    with pytest.raises(ValueError, match="Unknown city"):
        build_city_graph("Atlantis")


def test_no_two_cities_share_the_exact_same_center():
    """A sanity check that the new cities actually have distinct,
    real coordinate data rather than accidentally-copy-pasted ones."""
    centers = [_city_center(c) for c in list_cities()]
    assert len(set(centers)) == len(centers)
