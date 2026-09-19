"""Unit tests for ClassicalRuleBasedController decision logic."""

from traffic_optimizer.config import SignalPhase
from traffic_optimizer.controllers.signal_controller import ClassicalRuleBasedController
from traffic_optimizer.models.traffic_state import (
    IntersectionStateSnapshot,
    NetworkTrafficState,
)


def test_classical_controller_chooses_higher_demand_direction():
    controller = ClassicalRuleBasedController()

    # EW higher demand (E=20, W=15 => 35) vs NS (N=5, S=5 => 10)
    snap_ew_higher = IntersectionStateSnapshot(
        intersection_id="I1",
        queue_lengths={"N": 5, "S": 5, "E": 20, "W": 15},
        densities={"N": 0.05, "S": 0.05, "E": 0.2, "W": 0.15},
        capacities={"N": 100, "S": 100, "E": 100, "W": 100},
        current_phase="NS",
        current_green_duration=30,
        emergency_status={"N": False, "S": False, "E": False, "W": False},
    )

    state = NetworkTrafficState(timestamp=0.0, intersections={"I1": snap_ew_higher})
    decisions = controller.get_decisions(state)

    assert decisions["I1"].phase == SignalPhase.EAST_WEST
    assert decisions["I1"].duration == 60  # Total demand 35 => 60s discrete duration


def test_classical_controller_emergency_override():
    controller = ClassicalRuleBasedController()

    # EW higher queue, but NS has emergency vehicle
    snap_emergency = IntersectionStateSnapshot(
        intersection_id="I1",
        queue_lengths={"N": 2, "S": 2, "E": 40, "W": 40},
        densities={"N": 0.02, "S": 0.02, "E": 0.4, "W": 0.4},
        capacities={"N": 100, "S": 100, "E": 100, "W": 100},
        current_phase="EW",
        current_green_duration=30,
        emergency_status={"N": True, "S": False, "E": False, "W": False},
    )

    state = NetworkTrafficState(timestamp=0.0, intersections={"I1": snap_emergency})
    decisions = controller.get_decisions(state)

    assert decisions["I1"].phase == SignalPhase.NORTH_SOUTH
