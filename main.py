"""Main demonstration script for Quantum-Enhanced Adaptive Urban Traffic Optimization foundation."""

import sys
from traffic_optimizer.network.traffic_network import TrafficNetwork
from traffic_optimizer.controllers.signal_controller import ClassicalRuleBasedController
from traffic_optimizer.simulation.traffic_simulator import TrafficSimulator
from traffic_optimizer.config import SignalPhase, ALLOWED_GREEN_DURATIONS


def print_separator(title: str = "") -> None:
    if title:
        print(f"\n{'=' * 25} {title} {'=' * 25}")
    else:
        print(f"{'=' * 65}")


def print_traffic_state(state, step_idx: int) -> None:
    """Formats and prints network state snapshots in clean CLI format."""
    print(f"\n--- Simulation Step {step_idx} (Time: {state.timestamp}s) ---")
    header = f"{'Intersection':<14} | {'Phase':<6} | {'Green Time':<10} | {'Queues (N/S/E/W)':<20} | {'Emergency'}"
    print(header)
    print("-" * len(header))

    for iid, snap in state.intersections.items():
        q = snap.queue_lengths
        q_str = f"N:{q['N']:<2} S:{q['S']:<2} E:{q['E']:<2} W:{q['W']:<2}"
        emerg = [d for d, has in snap.emergency_status.items() if has]
        emerg_str = ", ".join(emerg) if emerg else "None"

        print(
            f"{snap.intersection_id:<14} | {snap.current_phase:<6} | {snap.current_green_duration:<10}s | {q_str:<20} | {emerg_str}"
        )


def main() -> None:
    print_separator("Quantum-Enhanced Adaptive Urban Traffic Optimization (Foundation)")
    print("Initializing 4-intersection urban traffic network grid (I1 - I4)...")

    # 1. Create 2x2 grid network (I1, I2, I3, I4)
    network = TrafficNetwork.create_grid_network(rows=2, cols=2, default_capacity=100)

    # 2. Seed initial queues to simulate non-uniform traffic demand
    i1 = network.get_intersection("I1")
    i1.set_queue_length("N", 25)
    i1.set_queue_length("S", 20)
    i1.set_queue_length("E", 5)
    i1.set_queue_length("W", 8)

    i2 = network.get_intersection("I2")
    i2.set_queue_length("N", 8)
    i2.set_queue_length("S", 10)
    i2.set_queue_length("E", 35)
    i2.set_queue_length("W", 30)

    i3 = network.get_intersection("I3")
    i3.set_queue_length("N", 4)
    i3.set_queue_length("S", 2)
    i3.set_queue_length("E", 12)
    i3.set_queue_length("W", 18)

    i4 = network.get_intersection("I4")
    i4.set_queue_length("N", 30)
    i4.set_queue_length("S", 28)
    i4.set_queue_length("E", 3)
    i4.set_queue_length("W", 2)

    # 3. Instantiate Classical Rule-Based Controller & Traffic Simulator
    controller = ClassicalRuleBasedController()
    simulator = TrafficSimulator(
        network=network,
        controller=controller,
        seed=42,
        timestep=5,
        arrival_rate_max=4,
        discharge_rate=1,
    )

    # 4. Print Initial Traffic State
    initial_state = network.get_state_snapshot(timestamp=0.0)
    print_traffic_state(initial_state, step_idx=0)

    # 5. Run Simulation Loop for 10 Steps
    print_separator("Executing Simulation Steps (Classical Controller)")

    num_steps = 10
    for step in range(1, num_steps + 1):
        updated_state = simulator.step()

        # Query controller decisions to log
        decisions = controller.get_decisions(updated_state)
        decisions_summary = ", ".join(
            [f"{iid}: {d.phase.value} ({d.duration}s)" for iid, d in decisions.items()]
        )
        print(f"\n[Step {step}] Controller Decisions -> {decisions_summary}")

        print_traffic_state(updated_state, step_idx=step)

    print_separator("Simulation Run Complete")
    print("Baseline classical controller successfully managed signal phases & green durations.")
    print("The traffic state snapshot interface is ready to accept future QUBO / QAOA quantum optimizers.")


if __name__ == "__main__":
    main()
