"""Unit test suite for QAOA solver, Ising conversion, bitstring ordering, and controller integration."""

import pytest
import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from traffic_optimizer.config import QUBOConfig, SignalPhase
from traffic_optimizer.models.traffic_state import IntersectionStateSnapshot, NetworkTrafficState
from traffic_optimizer.network.traffic_network import TrafficNetwork
from traffic_optimizer.optimization.qubo import QUBOProblem, TrafficQUBOBuilder
from traffic_optimizer.quantum.ising_converter import IsingConverter, IsingHamiltonian
from traffic_optimizer.quantum.qaoa_solver import QAOASolver
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController


def test_ising_conversion_1var_equivalence():
    # C(x1) = 5 x1 + 10 => Q11 = 5, offset = 10
    qubo = QUBOProblem(
        num_variables=1,
        var_names=["x0"],
        var_map={"x0": 0},
        index_to_var={0: "x0"},
        Q_matrix={(0, 0): 5.0},
        constant_offset=10.0,
    )
    ising = IsingConverter.qubo_to_ising(qubo)

    # For x0=0 => Z0=+1 => C(0)=10, H(+1)=10
    assert qubo.evaluate_cost("0") == ising.evaluate_energy("0") == 10.0
    # For x0=1 => Z0=-1 => C(1)=15, H(-1)=15
    assert qubo.evaluate_cost("1") == ising.evaluate_energy("1") == 15.0


def test_ising_conversion_2var_equivalence():
    # C(x1, x2) = 2 x1 + 4 x2 + 8 x1 x2 + 3
    qubo = QUBOProblem(
        num_variables=2,
        var_names=["x0", "x1"],
        var_map={"x0": 0, "x1": 1},
        index_to_var={0: "x0", 1: "x1"},
        Q_matrix={(0, 0): 2.0, (1, 1): 4.0, (0, 1): 8.0},
        constant_offset=3.0,
    )
    ising = IsingConverter.qubo_to_ising(qubo)

    for bitstr in ["00", "10", "01", "11"]:
        qubo_val = qubo.evaluate_cost(bitstr)
        ising_val = ising.evaluate_energy(bitstr)
        assert pytest.approx(qubo_val, abs=1e-5) == ising_val


def test_qaoa_circuit_building_and_aer_execution():
    solver = QAOASolver(p_layers=2, shots=100, seed=42)
    ising = IsingHamiltonian(
        num_qubits=3,
        linear_z={0: 1.0, 1: -2.0},
        quadratic_zz={(0, 1): 0.5},
        offset=5.0,
    )

    qc = solver.build_qaoa_circuit(ising, gamma=[0.1, 0.2], beta=[0.3, 0.4])
    assert qc.num_qubits == 3

    # Verify execution on Aer
    qc.measure_all()
    backend = AerSimulator(seed_simulator=42)
    job = backend.run(qc, shots=100)
    counts = job.result().get_counts()
    assert sum(counts.values()) == 100


def test_qiskit_bitstring_endianness_reversing():
    qiskit_str = "100"  # In Qiskit, q[0] is '0' (rightmost) and q[2] is '1' (leftmost)
    reversed_str = QAOASolver.reverse_qiskit_bitstring(qiskit_str)
    assert reversed_str == "001"  # Position 0 has '0', position 2 has '1'


def test_feasibility_checking():
    net = TrafficNetwork.create_grid_network(rows=1, cols=1)  # 1 intersection => 6 variables
    state = net.get_state_snapshot()
    qubo = TrafficQUBOBuilder().build_qubo(state)

    # Valid 1-hot bitstring
    assert QAOASolver.check_feasibility("100000", qubo) is True
    assert QAOASolver.check_feasibility("000100", qubo) is True

    # Invalid 0-hot bitstring
    assert QAOASolver.check_feasibility("000000", qubo) is False
    # Invalid 2-hot bitstring
    assert QAOASolver.check_feasibility("110000", qubo) is False


def test_small_qubo_qaoa_optimization_and_sampling():
    # Single intersection test case
    net = TrafficNetwork.create_grid_network(rows=1, cols=1)
    i1 = net.get_intersection("I1")
    i1.set_queue_length("N", 25)
    i1.set_queue_length("S", 25)  # Heavy NS demand

    state = net.get_state_snapshot()
    qubo = TrafficQUBOBuilder().build_qubo(state)

    solver = QAOASolver(p_layers=1, shots=512, maxiter=20, seed=42)
    result = solver.solve(qubo)

    assert result.shots == 512
    assert result.p_layers == 1
    assert len(result.optimal_gamma) == 1
    assert len(result.optimal_beta) == 1
    assert len(result.selected_bitstring) == 6
    assert result.is_feasible is True
    assert result.qubo_cost < 100.0  # Feasible low-cost solution selected


def test_quantum_controller_end_to_end_integration():
    net = TrafficNetwork.create_grid_network(rows=2, cols=2)  # 4 intersections (24 qubits)
    state = net.get_state_snapshot()

    controller = QuantumOptimizerController(
        p_layers=1, shots=256, maxiter=10, seed=42
    )

    decisions = controller.get_decisions(state)
    assert len(decisions) == 4
    assert "I1" in decisions
    assert "I4" in decisions
    assert decisions["I1"].phase in (SignalPhase.NORTH_SOUTH, SignalPhase.EAST_WEST)
    assert decisions["I1"].duration in (30, 60, 90)

    res = controller.last_result
    assert res is not None
    assert res.is_feasible is True
    assert res.backend_name == "aer_simulator"
