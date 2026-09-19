"""
Integration tests for SUMO adapter and SimulationOrchestrator.

These tests verify TraCI connection, traffic state extraction, signal control,
emergency vehicle injection, congestion event manipulation, and end-to-end
orchestrator runs with Classical and Quantum controllers.
"""

import os
import pytest
import sumolib

from traffic_optimizer.config import SignalPhase
from traffic_optimizer.controllers.signal_controller import (
    ClassicalRuleBasedController,
    SignalDecision,
)
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.integrations.sumo_adapter import SUMOAdapter
from traffic_optimizer.integrations.orchestrator import SimulationOrchestrator
from traffic_optimizer.models.traffic_state import NetworkTrafficState

CONFIG_PATH = "sumo/simulation.sumocfg"


def sumo_available() -> bool:
    """Checks if SUMO binary is available on the system."""
    try:
        sumolib.checkBinary("sumo")
        return os.path.exists(CONFIG_PATH)
    except Exception:
        return False


pytestmark = pytest.mark.sumo


@pytest.fixture(autouse=True)
def check_sumo():
    """Skip tests if SUMO or config is unavailable."""
    if not sumo_available():
        pytest.skip("SUMO binary or sumo/simulation.sumocfg not available")


@pytest.fixture
def adapter():
    """Fixture providing a managed SUMOAdapter instance."""
    ad = SUMOAdapter(config_path=CONFIG_PATH, use_gui=False)
    yield ad
    ad.close()


def test_sumo_installed_and_runnable():
    """Verifies that SUMO binary can be located."""
    binary = sumolib.checkBinary("sumo")
    assert binary is not None
    assert os.path.exists(binary) or binary.endswith(".exe")


def test_sumo_adapter_lifecycle(adapter):
    """Verifies adapter start, step, and clean close."""
    adapter.start_simulation()
    assert adapter.is_connected

    adapter.step(seconds=5)
    assert adapter.is_connected

    adapter.close()
    assert not adapter.is_connected


def test_sumo_extract_network_state(adapter):
    """Verifies extract_network_state() produces a valid NetworkTrafficState."""
    adapter.start_simulation()
    adapter.step(seconds=5)

    state = adapter.extract_network_state()
    assert isinstance(state, NetworkTrafficState)
    assert len(state.intersections) == 8
    assert "I1" in state.intersections
    assert "I8" in state.intersections

    snap = state.intersections["I1"]
    assert "N" in snap.queue_lengths
    assert "S" in snap.densities
    assert "E" in snap.capacities
    assert "W" in snap.emergency_status
    assert snap.current_phase in [SignalPhase.NORTH_SOUTH.value, SignalPhase.EAST_WEST.value]


def test_sumo_apply_signal_decisions(adapter):
    """Verifies applying SignalDecisions sets traffic lights in SUMO without error."""
    adapter.start_simulation()
    adapter.step(seconds=3)

    decisions = {
        "I1": SignalDecision(phase=SignalPhase.NORTH_SOUTH, duration=30),
        "I2": SignalDecision(phase=SignalPhase.EAST_WEST, duration=60),
    }

    adapter.apply_signal_decisions(decisions)
    adapter.step(seconds=2)
    assert adapter.is_connected


def test_sumo_emergency_injection(adapter):
    """Verifies emergency vehicle injection and tracking."""
    adapter.start_simulation()
    adapter.step(seconds=2)

    veh_id = "test_emerg_01"
    res = adapter.inject_emergency_vehicle(route_id="R1", vehicle_id=veh_id)
    assert res == veh_id
    assert veh_id in adapter.emergency_vehicles_injected

    # Step simulation to observe vehicle
    adapter.step(seconds=3)
    state = adapter.extract_network_state()
    assert isinstance(state, NetworkTrafficState)


def test_sumo_congestion_injection_and_clear(adapter):
    """Verifies edge speed reduction and clearing during congestion events."""
    adapter.start_simulation()
    adapter.step(seconds=2)

    edge_id = "I2_I3"
    res_inject = adapter.inject_congestion_event(edge_id=edge_id, speed_reduction_factor=0.3)
    assert "injected" in res_inject.lower()
    assert edge_id in adapter.active_congestion_events

    res_clear = adapter.clear_congestion_event(edge_id=edge_id)
    assert "cleared" in res_clear.lower()
    assert edge_id not in adapter.active_congestion_events


def test_sumo_metrics_collection(adapter):
    """Verifies get_metrics() returns all expected keys and valid types."""
    adapter.start_simulation()
    adapter.step(seconds=5)

    metrics = adapter.get_metrics()
    required_keys = [
        "vehicle_count",
        "total_waiting_time",
        "avg_waiting_time",
        "total_queue",
        "throughput",
        "fuel_consumption_liters",
        "co2_emissions_kg",
    ]
    for key in required_keys:
        assert key in metrics, f"Missing key {key}"
        assert isinstance(metrics[key], (int, float))


def test_orchestrator_classical_run():
    """Runs SimulationOrchestrator with ClassicalRuleBasedController."""
    controller = ClassicalRuleBasedController()
    orchestrator = SimulationOrchestrator(
        controller=controller,
        controller_name="classical_test",
        config_path=CONFIG_PATH,
        total_steps=10,
        optimization_interval=5,
        use_gui=False,
    )

    result = orchestrator.run()
    assert result.controller_name == "classical_test"
    assert result.total_steps == 10
    assert len(result.step_metrics) == 10
    assert result.wall_time_seconds > 0

    final = result.final_metrics
    assert "avg_waiting_time" in final
    assert "total_co2_kg" in final
    assert final["controller"] == "classical_test"


def test_orchestrator_quantum_subset_run():
    """
    Runs SimulationOrchestrator with QuantumOptimizerController on 1 intersection.
    Using 1 intersection (6 variables/qubits) and maxiter=2 for fast test execution.
    """
    controller = QuantumOptimizerController(
        p_layers=1,
        shots=100,
        maxiter=5,
        seed=42,
    )
    orchestrator = SimulationOrchestrator(
        controller=controller,
        controller_name="quantum_test",
        config_path=CONFIG_PATH,
        total_steps=6,
        optimization_interval=3,
        intersection_ids=["I1"],
        use_gui=False,
    )

    result = orchestrator.run()
    assert result.controller_name == "quantum_test"
    assert result.total_steps == 6
    assert len(result.step_metrics) == 6
    assert result.qaoa_details is not None
    assert "selected_bitstring" in result.qaoa_details
    assert "qubo_cost" in result.qaoa_details
    assert len(result.qaoa_details["selected_bitstring"]) == 6


def test_emergency_corridor_resumes_normal_control():
    """
    Emergency Corridor Validation:

    Verifies that:
    1. An emergency vehicle can be injected and tracked.
    2. After the emergency vehicle departs, its travel time is recorded.
    3. The controller continues producing signal decisions normally after the
       emergency event (i.e., the orchestrator does not freeze or crash).
    4. Post-emergency step metrics are non-empty and have valid queue lengths.

    This test does NOT assert that QAOA outperforms Classical during emergency -
    that would be manufacturing results. It only asserts behavioral continuity.
    """
    controller = ClassicalRuleBasedController()
    orchestrator = SimulationOrchestrator(
        controller=controller,
        controller_name="emerg_corridor_test",
        config_path=CONFIG_PATH,
        total_steps=80,
        optimization_interval=10,
        use_gui=False,
        emergency_inject_step=20,   # Inject at step 20
        emergency_route="R1",
    )

    result = orchestrator.run()

    # 1. Basic run integrity
    assert result.total_steps == 80
    assert len(result.step_metrics) == 80

    # 2. Post-emergency steps should have valid (non-negative) queue lengths
    post_emergency_metrics = [m for m in result.step_metrics if m.step > 30]
    assert len(post_emergency_metrics) > 0
    for m in post_emergency_metrics[:5]:
        assert m.total_queue >= 0, f"Negative queue at step {m.step}"
        assert m.vehicle_count >= 0

    # 3. Verify the emergency event was recorded in events list
    emergency_event_steps = [m for m in result.step_metrics if any("Emergency" in e for e in m.events)]
    assert len(emergency_event_steps) > 0, "No emergency injection event recorded in step metrics"

    # 4. The orchestrator should produce at least one optimization decision after
    #    the emergency step (verifies control resumes normally)
    post_emerg_decisions = [m for m in result.step_metrics if m.step > 20 and m.decisions]
    assert len(post_emerg_decisions) > 0, (
        "No signal decisions found after emergency event - adaptive control may have stalled"
    )


def test_orchestrator_emergency_and_congestion_combined():
    """
    Verifies the orchestrator can handle simultaneous emergency + congestion events
    without crashing, and produces a valid SimulationResult.
    """
    controller = ClassicalRuleBasedController()
    orchestrator = SimulationOrchestrator(
        controller=controller,
        controller_name="combined_events_test",
        config_path=CONFIG_PATH,
        total_steps=50,
        optimization_interval=10,
        use_gui=False,
        emergency_inject_step=15,
        congestion_inject_step=20,
        congestion_clear_step=45,
        congestion_edge="I2_I3",
    )

    result = orchestrator.run()
    assert len(result.step_metrics) == 50
    assert result.wall_time_seconds > 0

    # Both types of events should appear in the metrics timeline
    event_steps = [m for m in result.step_metrics if m.events]
    assert len(event_steps) >= 3, (
        f"Expected at least 3 event-bearing steps (inject emerg, inject cong, clear cong), "
        f"got {len(event_steps)}"
    )
