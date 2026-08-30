import numpy as np
import pytest

from congestion import apply_congestion_to_matrix
from traffic_provider import (
    LiveTrafficProviderStub,
    SimulatedTrafficProvider,
    get_traffic_provider,
)


def test_get_traffic_provider_simulated_matches_direct_call():
    W = np.array([[0, 10, 20], [10, 0, 15], [20, 15, 0]], dtype=float)
    provider = get_traffic_provider("simulated")
    assert isinstance(provider, SimulatedTrafficProvider)
    assert np.allclose(
        provider.get_congested_matrix(W, hour=18.5),
        apply_congestion_to_matrix(W, hour=18.5),
    )


def test_get_traffic_provider_live_stub_raises_clearly():
    provider = get_traffic_provider("live")
    assert isinstance(provider, LiveTrafficProviderStub)
    W = np.array([[0, 10], [10, 0]], dtype=float)
    with pytest.raises(NotImplementedError):
        provider.get_congested_matrix(W, hour=9.0)


def test_get_traffic_provider_unknown_name_raises_value_error():
    with pytest.raises(ValueError):
        get_traffic_provider("some_provider_that_does_not_exist")
