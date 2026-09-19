"""Unit tests for TrafficState snapshot representations."""

from traffic_optimizer.models.traffic_state import (
    IntersectionStateSnapshot,
    NetworkTrafficState,
)


def test_intersection_state_snapshot_immutability_and_serialization():
    snap = IntersectionStateSnapshot(
        intersection_id="I1",
        queue_lengths={"N": 10, "S": 5, "E": 20, "W": 0},
        densities={"N": 0.1, "S": 0.05, "E": 0.2, "W": 0.0},
        capacities={"N": 100, "S": 100, "E": 100, "W": 100},
        current_phase="NS",
        current_green_duration=60,
        emergency_status={"N": False, "S": False, "E": False, "W": False},
    )

    d = snap.to_dict()
    assert d["intersection_id"] == "I1"
    assert d["queue_lengths"]["N"] == 10
    assert d["current_phase"] == "NS"
    assert d["current_green_duration"] == 60


def test_network_traffic_state_snapshot():
    snap_i1 = IntersectionStateSnapshot(
        intersection_id="I1",
        queue_lengths={"N": 0, "S": 0, "E": 0, "W": 0},
        densities={"N": 0.0, "S": 0.0, "E": 0.0, "W": 0.0},
        capacities={"N": 100, "S": 100, "E": 100, "W": 100},
        current_phase="NS",
        current_green_duration=30,
        emergency_status={"N": False, "S": False, "E": False, "W": False},
    )
    net_state = NetworkTrafficState(
        timestamp=5.0,
        intersections={"I1": snap_i1},
        road_vehicle_counts={"R1": 15},
    )

    assert net_state.timestamp == 5.0
    assert net_state.get_intersection("I1").intersection_id == "I1"
    dict_repr = net_state.to_dict()
    assert "intersections" in dict_repr
    assert dict_repr["road_vehicle_counts"]["R1"] == 15
