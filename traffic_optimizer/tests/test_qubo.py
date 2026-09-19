"""Comprehensive test suite for QUBO builder, cost models, penalties, and decoder."""

import pytest
import numpy as np

from traffic_optimizer.config import QUBOConfig, SignalPhase
from traffic_optimizer.models.intersection import Intersection
from traffic_optimizer.models.traffic_state import (
    IntersectionStateSnapshot,
    NetworkTrafficState,
)
from traffic_optimizer.network.traffic_network import TrafficNetwork
from traffic_optimizer.optimization.cost_model import TrafficCostModel
from traffic_optimizer.optimization.qubo import (
    TrafficQUBOBuilder,
    TrafficQUBODecoder,
    QUBOProblem,
)


def test_variable_count_scaling_4_and_8_intersections():
    # 4 Intersections (2x2 grid) => 4 * 6 = 24 binary variables
    net4 = TrafficNetwork.create_grid_network(rows=2, cols=2)
    state4 = net4.get_state_snapshot()
    builder = TrafficQUBOBuilder()
    qubo4 = builder.build_qubo(state4)
    assert qubo4.num_variables == 24
    assert len(qubo4.var_names) == 24

    # 8 Intersections (2x4 grid) => 8 * 6 = 48 binary variables
    net8 = TrafficNetwork.create_grid_network(rows=2, cols=4)
    state8 = net8.get_state_snapshot()
    qubo8 = builder.build_qubo(state8)
    assert qubo8.num_variables == 48
    assert len(qubo8.var_names) == 48


def test_exactly_one_penalty_evaluation():
    net = TrafficNetwork.create_grid_network(rows=1, cols=1)  # 1 intersection => 6 variables
    state = net.get_state_snapshot()
    config = QUBOConfig(lambda_penalty=1000.0)
    builder = TrafficQUBOBuilder(config=config)
    qubo = builder.build_qubo(state)

    # Candidate 1-hot bitstring (exactly 1 configuration selected)
    bitstring_1hot = "100000"
    cost_1hot = qubo.evaluate_cost(bitstring_1hot)

    # 0-hot bitstring (no configuration selected)
    bitstring_0hot = "000000"
    cost_0hot = qubo.evaluate_cost(bitstring_0hot)

    # 2-hot bitstring (two configurations selected)
    bitstring_2hot = "110000"
    cost_2hot = qubo.evaluate_cost(bitstring_2hot)

    # Exactly-one constraint penalty should be lowest for 1-hot
    # 0-hot adds lambda (1000), 2-hot adds lambda (1000)
    assert cost_0hot > cost_1hot
    assert cost_2hot > cost_1hot
    assert pytest.approx(cost_0hot - cost_1hot, abs=10.0) == 1000.0


def test_traffic_sensitivity_ns_vs_ew_demand():
    config = QUBOConfig(lambda_penalty=0.0)  # Ignore penalty to test objective traffic cost
    builder = TrafficQUBOBuilder(config=config)

    # State A: NS queue = 30, EW queue = 4
    snap_a = IntersectionStateSnapshot(
        intersection_id="I1",
        queue_lengths={"N": 15, "S": 15, "E": 2, "W": 2},
        densities={"N": 0.15, "S": 0.15, "E": 0.02, "W": 0.02},
        capacities={"N": 100, "S": 100, "E": 100, "W": 100},
        current_phase="NS",
        current_green_duration=30,
        emergency_status={"N": False, "S": False, "E": False, "W": False},
    )
    state_a = NetworkTrafficState(timestamp=0.0, intersections={"I1": snap_a})
    qubo_a = builder.build_qubo(state_a)

    # Cost of choosing NS vs EW
    cost_ns_a = qubo_a.evaluate_cost("100000")  # (NS, 30)
    cost_ew_a = qubo_a.evaluate_cost("000100")  # (EW, 30)
    assert cost_ns_a < cost_ew_a  # NS phase should be significantly cheaper

    # State B: NS queue = 4, EW queue = 30
    snap_b = IntersectionStateSnapshot(
        intersection_id="I1",
        queue_lengths={"N": 2, "S": 2, "E": 15, "W": 15},
        densities={"N": 0.02, "S": 0.02, "E": 0.15, "W": 0.15},
        capacities={"N": 100, "S": 100, "E": 100, "W": 100},
        current_phase="NS",
        current_green_duration=30,
        emergency_status={"N": False, "S": False, "E": False, "W": False},
    )
    state_b = NetworkTrafficState(timestamp=0.0, intersections={"I1": snap_b})
    qubo_b = builder.build_qubo(state_b)

    cost_ns_b = qubo_b.evaluate_cost("100000")
    cost_ew_b = qubo_b.evaluate_cost("000100")
    assert cost_ew_b < cost_ns_b  # EW phase should be significantly cheaper


def test_duration_sensitivity():
    config = QUBOConfig(lambda_penalty=0.0)
    builder = TrafficQUBOBuilder(config=config)

    # High queue (50 vehicles on NS) -> 90s duration should be preferred over 30s duration
    snap_heavy = IntersectionStateSnapshot(
        intersection_id="I1",
        queue_lengths={"N": 25, "S": 25, "E": 0, "W": 0},
        densities={"N": 0.25, "S": 0.25, "E": 0.0, "W": 0.0},
        capacities={"N": 100, "S": 100, "E": 100, "W": 100},
        current_phase="NS",
        current_green_duration=30,
        emergency_status={"N": False, "S": False, "E": False, "W": False},
    )
    state = NetworkTrafficState(timestamp=0.0, intersections={"I1": snap_heavy})
    qubo = builder.build_qubo(state)

    cost_30s = qubo.evaluate_cost("100000")  # (NS, 30)
    cost_90s = qubo.evaluate_cost("001000")  # (NS, 90)
    assert cost_90s < cost_30s


def test_emergency_sensitivity():
    config = QUBOConfig(lambda_penalty=0.0, w_emergency=500.0)
    builder = TrafficQUBOBuilder(config=config)

    # EW has higher queue (40 vs 4), but NS has Emergency vehicle
    snap_emergency = IntersectionStateSnapshot(
        intersection_id="I1",
        queue_lengths={"N": 2, "S": 2, "E": 20, "W": 20},
        densities={"N": 0.02, "S": 0.02, "E": 0.2, "W": 0.2},
        capacities={"N": 100, "S": 100, "E": 100, "W": 100},
        current_phase="EW",
        current_green_duration=30,
        emergency_status={"N": True, "S": False, "E": False, "W": False},
    )
    state = NetworkTrafficState(timestamp=0.0, intersections={"I1": snap_emergency})
    qubo = builder.build_qubo(state)

    cost_ns = qubo.evaluate_cost("100000")  # (NS, 30)
    cost_ew = qubo.evaluate_cost("000100")  # (EW, 30)
    assert cost_ns < cost_ew  # Emergency on NS overrides EW queue preference


def test_qubo_matrix_validity_and_determinism():
    net = TrafficNetwork.create_grid_network(rows=2, cols=2)
    state = net.get_state_snapshot()
    builder = TrafficQUBOBuilder()

    qubo1 = builder.build_qubo(state)
    qubo2 = builder.build_qubo(state)

    # Check finite numbers, no NaN, no Inf
    dense_mat = qubo1.to_dense_matrix()
    assert np.all(np.isfinite(dense_mat))

    # Check deterministic output
    assert qubo1.Q_matrix == qubo2.Q_matrix
    assert qubo1.constant_offset == qubo2.constant_offset


def test_bitstring_decoder():
    net = TrafficNetwork.create_grid_network(rows=2, cols=2)
    state = net.get_state_snapshot()
    builder = TrafficQUBOBuilder()
    qubo = builder.build_qubo(state)

    # Bitstring selecting:
    # I1: (NS, 60) -> 2nd bit in I1 group -> '010000'
    # I2: (EW, 30) -> 4th bit in I2 group -> '000100'
    # I3: (NS, 30) -> 1st bit in I3 group -> '100000'
    # I4: (EW, 90) -> 6th bit in I4 group -> '000001'
    bitstring = "010000000100100000000001"

    decisions = TrafficQUBODecoder.decode(bitstring, qubo)
    assert len(decisions) == 4
    assert decisions["I1"].phase == SignalPhase.NORTH_SOUTH
    assert decisions["I1"].duration == 60
    assert decisions["I2"].phase == SignalPhase.EAST_WEST
    assert decisions["I2"].duration == 30
    assert decisions["I3"].phase == SignalPhase.NORTH_SOUTH
    assert decisions["I3"].duration == 30
    assert decisions["I4"].phase == SignalPhase.EAST_WEST
    assert decisions["I4"].duration == 90
