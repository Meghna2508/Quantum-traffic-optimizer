"""Unit tests for TrafficSimulator dynamics (queue accumulation on red, discharge on green)."""

from traffic_optimizer.config import SignalPhase
from traffic_optimizer.controllers.signal_controller import ClassicalRuleBasedController
from traffic_optimizer.network.traffic_network import TrafficNetwork
from traffic_optimizer.simulation.traffic_simulator import TrafficSimulator


def test_traffic_simulator_queue_dynamics():
    net = TrafficNetwork.create_grid_network(rows=2, cols=2)
    controller = ClassicalRuleBasedController()
    sim = TrafficSimulator(
        network=net,
        controller=controller,
        seed=123,
        timestep=5,
        arrival_rate_max=2,
        discharge_rate=2,
    )

    # Force initial queue on I1: NS active GREEN, EW active RED
    i1 = net.get_intersection("I1")
    i1.set_signal_decision(SignalPhase.NORTH_SOUTH, 30)
    i1.set_queue_length("N", 20)
    i1.set_queue_length("E", 10)

    # Initial state
    assert i1.queue_lengths["N"] == 20
    assert i1.queue_lengths["E"] == 10

    # Step simulation: 5s timestep
    # On GREEN (NS): queue discharges (20 + arrivals - 2*5)
    # On RED (EW): queue increases (10 + arrivals)
    new_state = sim.step()
    i1_snap = new_state.get_intersection("I1")

    # Queue on GREEN (N) should decrease
    assert i1_snap.queue_lengths["N"] < 20
    # Queue on RED (E) should increase
    assert i1_snap.queue_lengths["E"] > 10


def test_traffic_simulator_multi_step_run():
    net = TrafficNetwork.create_grid_network(rows=2, cols=2)
    controller = ClassicalRuleBasedController()
    sim = TrafficSimulator(
        network=net,
        controller=controller,
        seed=42,
        timestep=5,
    )

    for _ in range(5):
        state = sim.step()

    assert state.timestamp == 25.0
    assert sim.step_count == 5
