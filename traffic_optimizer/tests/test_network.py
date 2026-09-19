"""Unit tests for TrafficNetwork model and grid scaling."""

import pytest
from traffic_optimizer.network.traffic_network import TrafficNetwork
from traffic_optimizer.models.intersection import Intersection
from traffic_optimizer.models.road import Road


def test_4_intersection_grid_creation():
    net = TrafficNetwork.create_grid_network(rows=2, cols=2)
    assert len(net.intersections) == 4
    assert "I1" in net.intersections
    assert "I2" in net.intersections
    assert "I3" in net.intersections
    assert "I4" in net.intersections

    # Check network graph connectivity
    assert net.graph.has_edge("I1", "I2")
    assert net.graph.has_edge("I2", "I1")
    assert net.graph.has_edge("I1", "I3")
    assert net.graph.has_edge("I3", "I4")


def test_8_intersection_scaling():
    net = TrafficNetwork.create_grid_network(rows=2, cols=4)
    assert len(net.intersections) == 8
    assert "I8" in net.intersections
    assert net.graph.has_edge("I1", "I2")
    assert net.graph.has_edge("I4", "I8")


def test_state_snapshot_extraction():
    net = TrafficNetwork.create_grid_network(rows=2, cols=2)
    state = net.get_state_snapshot(timestamp=10.0)
    assert state.timestamp == 10.0
    assert len(state.intersections) == 4
    snap_i1 = state.get_intersection("I1")
    assert snap_i1.intersection_id == "I1"
    assert "N" in snap_i1.queue_lengths
