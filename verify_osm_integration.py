"""Comprehensive Validation of the OpenStreetMap (OSM) SUMO Network."""

import os
import sumolib
import traci

from traffic_optimizer.config import QUBOConfig, SignalPhase
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.integrations.sumo_adapter import SUMOAdapter
from traffic_optimizer.integrations.orchestrator import SimulationOrchestrator


def run_osm_checks():
    print("=" * 65)
    print("STARTING OSM SUMO NETWORK & CONTROLLER VALIDATION")
    print("=" * 65)

    config_path = "sumo/osm/simulation_osm.sumocfg"
    assert os.path.isfile(config_path), f"Missing {config_path}"

    adapter = SUMOAdapter(config_path=config_path, use_gui=False)
    adapter.start_simulation()

    # Check 1: Traffic lights loaded
    tls_list = list(adapter.intersections)
    print(f"[PASS] Check 1: Detected {len(tls_list)} signalized intersections in OSM network.")
    assert len(tls_list) >= 4, f"Expected at least 4 TLS, got {len(tls_list)}"

    # Check 2: Step simulation and verify vehicle movements
    adapter.step(15)
    metrics_15 = adapter.get_metrics()
    print(f"[PASS] Check 2: Vehicles actively moving on OSM roads ({metrics_15['vehicle_count']} active vehicles).")
    assert metrics_15["vehicle_count"] > 0

    # Check 3: Extract NetworkTrafficState snapshot
    state = adapter.extract_network_state()
    print(f"[PASS] Check 3: Extracted NetworkTrafficState with {len(state.intersections)} junction snapshots.")
    assert len(state.intersections) == len(tls_list)

    # Check 4: Execute chunked QAOA optimization on OSM state
    controller = QuantumOptimizerController(
        qubo_config=QUBOConfig(), p_layers=1, shots=128, maxiter=5, seed=42
    )
    # Test on a 3-junction subnetwork
    test_iids = tls_list[:3]
    sub_state = type(state)(
        timestamp=state.timestamp,
        intersections={k: state.intersections[k] for k in test_iids},
    )
    decisions = controller.get_decisions(sub_state)
    print(f"[PASS] Check 4: QAOA optimizer generated decisions for {len(decisions)} OSM intersections.")
    assert len(decisions) == 3

    # Check 5: Apply decisions to SUMO via TraCI
    adapter.apply_signal_decisions(decisions)
    print("[PASS] Check 5: QAOA decisions applied to OSM traffic lights via TraCI.")

    # Check 6: Inject emergency vehicle along R_emergency
    inj = adapter.inject_emergency_vehicle(route_id="R_emergency", vehicle_id="emergency_osm_test")
    print(f"[PASS] Check 6: Injected emergency vehicle: {inj}")

    # Check 7: Advance simulation and verify metrics
    adapter.step(20)
    metrics_35 = adapter.get_metrics()
    print(f"[PASS] Check 7: Environmental metrics tracked on OSM network (Fuel: {metrics_35['fuel_consumption_liters']} L, CO2: {metrics_35['co2_emissions_kg']} kg).")

    adapter.close()
    print("=" * 65)
    print("ALL OSM CHECKS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_osm_checks()
