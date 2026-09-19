"""Demonstration script showcasing end-to-end QAOA Quantum Optimization Engine."""

import sys
import time
from traffic_optimizer.network.traffic_network import TrafficNetwork
from traffic_optimizer.controllers.signal_controller import ClassicalRuleBasedController
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.simulation.traffic_simulator import TrafficSimulator


def print_banner(title: str) -> None:
    print(f"\n{'=' * 30} {title} {'=' * 30}")


def main() -> None:
    print_banner("Quantum-Enhanced Adaptive Urban Traffic Optimization (Phase 3 QAOA)")

    # 1. Build 4-intersection urban traffic grid
    print("\n[1] Initializing 4-Intersection Traffic Grid (I1 - I4)...")
    network = TrafficNetwork.create_grid_network(rows=2, cols=2, default_capacity=100)

    # Set initial non-uniform traffic queues
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

    # Print Initial Traffic State
    state = network.get_state_snapshot(timestamp=0.0)
    print("\n[2] Initial Network Traffic State Snapshot:")
    print(f"{'Intersection':<14} | {'Phase':<6} | {'Queues (N/S/E/W)'}")
    print("-" * 50)
    for iid, snap in state.intersections.items():
        q = snap.queue_lengths
        print(f"{iid:<14} | {snap.current_phase:<6} | N:{q['N']} S:{q['S']} E:{q['E']} W:{q['W']}")

    # 2. Instantiate Quantum Optimizer Controller
    print_banner("Instantiating QAOA Quantum Controller")
    p_layers = 1
    shots = 512
    maxiter = 25
    seed = 42

    print(f"  QAOA Circuit Layers (p) : {p_layers}")
    print(f"  Measurement Shots       : {shots}")
    print(f"  Classical Optimizer     : COBYLA (maxiter={maxiter})")
    print(f"  Qiskit Execution Backend: Qiskit AerSimulator (seed={seed})")

    quantum_controller = QuantumOptimizerController(
        p_layers=p_layers,
        shots=shots,
        maxiter=maxiter,
        seed=seed,
    )

    # 3. Execute Quantum Optimization Pipeline
    print_banner("Running QAOA Parameter Optimization & Quantum Circuit Execution")
    start_time = time.time()
    decisions = quantum_controller.get_decisions(state)
    total_time = time.time() - start_time

    res = quantum_controller.last_result
    assert res is not None

    print(f"\n[3] QAOA Quantum Optimization Results:")
    print(f"  Number of QUBO Variables: 24 (4 Intersections x 6 Configurations)")
    print(f"  Execution Time           : {res.execution_time_seconds}s")
    print(f"  Optimized Gamma (gamma)  : {res.optimal_gamma}")
    print(f"  Optimized Beta  (beta)   : {res.optimal_beta}")
    print(f"  Selected Bitstring       : {res.selected_bitstring}")
    print(f"  Evaluated QUBO Cost      : {res.qubo_cost}")
    print(f"  Constraint Feasible      : {res.is_feasible}")
    print(f"  Result Source            : {'CLASSICAL FALLBACK' if res.is_fallback else 'QAOA QUANTUM SAMPLER'}")

    if res.is_fallback:
        print(f"  Fallback Reason          : {res.fallback_reason}")

    # Top Sampled Bitstrings
    print("\n[4] Top 5 Sampled Bitstring Measurement Counts:")
    sorted_samples = sorted(res.sampled_bitstring_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    for bitstr, cnt in sorted_samples:
        print(f"  Bitstring '{bitstr[:12]}...{bitstr[-6:]}' -> {cnt} counts ({cnt/shots*100:.1f}%)")

    # 4. Decoded Signal Decisions
    print_banner("Decoded Signal Decisions (Phase & Green Duration)")
    for iid, dec in sorted(decisions.items()):
        print(f"  {iid}: Phase = {dec.phase.value:<2} | Green Duration = {dec.duration}s")

    # 5. Run Single Simulation Step with Quantum Decisions
    print_banner("Executing Simulation Step with Quantum Decisions")
    simulator = TrafficSimulator(network=network, controller=quantum_controller, seed=seed)
    updated_state = simulator.step()

    print("\nUpdated Network Traffic State Snapshot (After Quantum Step):")
    print(f"{'Intersection':<14} | {'Phase':<6} | {'Queues (N/S/E/W)'}")
    print("-" * 50)
    for iid, snap in updated_state.intersections.items():
        q = snap.queue_lengths
        print(f"{iid:<14} | {snap.current_phase:<6} | N:{q['N']} S:{q['S']} E:{q['E']} W:{q['W']}")

    print_banner("QAOA Quantum Optimization Demonstration Complete")


if __name__ == "__main__":
    main()
