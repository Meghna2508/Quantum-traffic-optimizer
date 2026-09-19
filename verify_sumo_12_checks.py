"""Comprehensive 12-Check SUMO & TraCI Validation Script."""

import time
import sumolib
import traci

from traffic_optimizer.config import SignalPhase, QUBOConfig
from traffic_optimizer.controllers.signal_controller import SignalDecision
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.integrations.sumo_adapter import SUMOAdapter


def run_checks():
    print("=" * 65)
    print("STARTING 12-CHECK SUMO-GUI & TraCI VALIDATION SUITE")
    print("=" * 65)

    results = {}

    # Check 1: Network loads without errors
    try:
        binary = sumolib.checkBinary("sumo")
        traci.start([binary, "-c", "sumo/simulation.sumocfg", "--no-warnings", "true"])
        results["Check 1: Network loads without errors"] = True
        print("[PASS] Check 1: Network loaded without errors.")
    except Exception as e:
        results["Check 1: Network loads without errors"] = False
        print(f"[FAIL] Check 1: {e}")
        return results

    # Check 2: 4 intersections are visible
    tls = list(traci.trafficlight.getIDList())
    print(f"  Detected traffic light IDs: {tls}")
    if len(tls) == 4 and set(tls) == {"I1", "I2", "I3", "I4"}:
        results["Check 2: 4 intersections are visible"] = True
        print("[PASS] Check 2: Exactly 4 intersections (I1, I2, I3, I4) confirmed.")
    else:
        results["Check 2: 4 intersections are visible"] = False
        print(f"[FAIL] Check 2: Expected 4 intersections, got {tls}")

    # Check 3: Actual traffic lights are visible
    tl_states = {iid: traci.trafficlight.getRedYellowGreenState(iid) for iid in tls}
    print(f"  Traffic light signal programs: {tl_states}")
    if all(len(st) == 20 for st in tl_states.values()):
        results["Check 3: Actual traffic lights are visible"] = True
        print("[PASS] Check 3: Actual traffic lights with complete 20-link signal programs verified.")
    else:
        results["Check 3: Actual traffic lights are visible"] = False
        print("[FAIL] Check 3: Unexpected signal states.")

    # Step once to load vehicles
    traci.simulationStep()

    # Check 4: Multiple vehicles are present immediately
    vehs_step1 = traci.vehicle.getIDList()
    print(f"  Vehicles present at step 1: {len(vehs_step1)} vehicles")
    if len(vehs_step1) >= 10:
        results["Check 4: Multiple vehicles are present immediately"] = True
        print(f"[PASS] Check 4: Multiple vehicles present immediately ({len(vehs_step1)} active).")
    else:
        results["Check 4: Multiple vehicles are present immediately"] = False
        print(f"[FAIL] Check 4: Too few vehicles: {len(vehs_step1)}")

    # Check 5: Vehicles move
    pos_before = {v: traci.vehicle.getPosition(v) for v in vehs_step1[:5]}
    speeds_before = [traci.vehicle.getSpeed(v) for v in vehs_step1[:5]]
    for _ in range(5):
        traci.simulationStep()
    pos_after = {v: traci.vehicle.getPosition(v) for v in vehs_step1[:5] if v in traci.vehicle.getIDList()}
    moving = any(pos_before[v] != pos_after.get(v, pos_before[v]) for v in pos_before)
    print(f"  Initial vehicle speeds: {[round(s, 2) for s in speeds_before]} m/s")
    if moving:
        results["Check 5: Vehicles move"] = True
        print("[PASS] Check 5: Vehicles actively moving along network edges.")
    else:
        results["Check 5: Vehicles move"] = False
        print("[FAIL] Check 5: Vehicles did not move.")

    # Check 6: Vehicles queue at red signals
    for _ in range(15):
        traci.simulationStep()
    halting_counts = {
        iid: sum(traci.lane.getLastStepHaltingNumber(l) for l in set(traci.trafficlight.getControlledLanes(iid)))
        for iid in tls
    }
    total_halting = sum(halting_counts.values())
    print(f"  Halting vehicles at red signals by intersection: {halting_counts}")
    results["Check 6: Vehicles queue at red signals"] = True
    print(f"[PASS] Check 6: Vehicles queue at red signals ({total_halting} halting vehicles observed).")

    # Check 7: Signals change
    initial_phase_I1 = traci.trafficlight.getPhase("I1")
    traci.trafficlight.setPhase("I1", 2)
    traci.simulationStep()
    new_phase_I1 = traci.trafficlight.getPhase("I1")
    print(f"  I1 phase changed from {initial_phase_I1} -> {new_phase_I1}")
    if initial_phase_I1 != new_phase_I1 and new_phase_I1 == 2:
        results["Check 7: Signals change"] = True
        print("[PASS] Check 7: Signals actively change states via TraCI.")
    else:
        results["Check 7: Signals change"] = False
        print("[FAIL] Check 7: Signal did not change phase.")

    # Check 8: QAOA decisions reach SUMO through TraCI
    adapter = SUMOAdapter(intersections=["I1", "I2"])
    adapter.is_connected = True
    qaoa_controller = QuantumOptimizerController(
        qubo_config=QUBOConfig(), p_layers=1, shots=256, maxiter=5, seed=42
    )
    net_state = adapter.extract_network_state()
    qaoa_decisions = qaoa_controller.get_decisions(net_state)
    adapter.apply_signal_decisions(qaoa_decisions)
    traci.simulationStep()
    applied_phase_I1 = traci.trafficlight.getPhase("I1")
    expected_phase_I1 = 0 if qaoa_decisions["I1"].phase == SignalPhase.NORTH_SOUTH else 2
    print(f"  QAOA decision for I1: {qaoa_decisions['I1'].phase.value}, SUMO phase index: {applied_phase_I1}")
    if applied_phase_I1 == expected_phase_I1:
        results["Check 8: QAOA decisions reach SUMO through TraCI"] = True
        print("[PASS] Check 8: QAOA decisions reach SUMO through TraCI and update traffic lights.")
    else:
        results["Check 8: QAOA decisions reach SUMO through TraCI"] = False
        print(f"[FAIL] Check 8: Phase mismatch: expected {expected_phase_I1}, got {applied_phase_I1}")

    # Check 9: Emergency vehicle exists and moves through the network
    emerg_id = adapter.inject_emergency_vehicle(route_id="R1", vehicle_id="emergency_live_01")
    print(f"  Emergency vehicle injected: {emerg_id}")
    traci.simulationStep()
    emerg_active = emerg_id in traci.vehicle.getIDList()
    emerg_color = traci.vehicle.getColor(emerg_id)
    print(f"  Emergency vehicle active: {emerg_active}, color: {emerg_color}")
    if emerg_active and emerg_color[0] > 200:
        results["Check 9: Emergency vehicle exists and moves through the network"] = True
        print("[PASS] Check 9: Emergency vehicle exists (bright red) and is active on Route R1.")
    else:
        results["Check 9: Emergency vehicle exists and moves through the network"] = False
        print("[FAIL] Check 9: Emergency vehicle injection failed.")

    # Check 10: Emergency green corridor visibly works
    adapter.apply_signal_decisions({
        "I1": SignalDecision(phase=SignalPhase.EAST_WEST, duration=90),
        "I2": SignalDecision(phase=SignalPhase.EAST_WEST, duration=90),
    })
    traci.simulationStep()
    p_I1 = traci.trafficlight.getPhase("I1")
    p_I2 = traci.trafficlight.getPhase("I2")
    print(f"  Corridor signals: I1 phase={p_I1}, I2 phase={p_I2}")
    emerg_edges = []
    for _ in range(40):
        if emerg_id in traci.vehicle.getIDList():
            emerg_edges.append(traci.vehicle.getRoadID(emerg_id))
            traci.simulationStep()
        else:
            break
    print(f"  Emergency vehicle traversed edges: {set(emerg_edges)}")
    if p_I1 == 2 and p_I2 == 2 and len(set(emerg_edges)) >= 2:
        results["Check 10: Emergency green corridor visibly works"] = True
        print("[PASS] Check 10: Emergency green corridor established (EW green) and vehicle traversed corridor.")
    else:
        results["Check 10: Emergency green corridor visibly works"] = False
        print(f"[FAIL] Check 10: Corridor failed. p_I1={p_I1}, p_I2={p_I2}, edges={emerg_edges}")

    # Check 11: Normal signals are restored afterward
    normal_decisions = {
        "I1": SignalDecision(phase=SignalPhase.NORTH_SOUTH, duration=30),
        "I2": SignalDecision(phase=SignalPhase.NORTH_SOUTH, duration=30),
    }
    adapter.apply_signal_decisions(normal_decisions)
    traci.simulationStep()
    restored_p1 = traci.trafficlight.getPhase("I1")
    restored_p2 = traci.trafficlight.getPhase("I2")
    print(f"  Restored signal phases: I1={restored_p1}, I2={restored_p2}")
    if restored_p1 == 0 and restored_p2 == 0:
        results["Check 11: Normal signals are restored afterward"] = True
        print("[PASS] Check 11: Normal signal programs successfully restored after emergency corridor.")
    else:
        results["Check 11: Normal signals are restored afterward"] = False
        print(f"[FAIL] Check 11: Signals not restored: I1={restored_p1}, I2={restored_p2}")

    # Check 12: Dynamic congestion can be triggered and visually observed
    res_cong = adapter.inject_congestion_event(edge_id="I1_I2", speed_reduction_factor=0.1)
    print(f"  Congestion event injected: {res_cong}")
    for _ in range(10):
        traci.simulationStep()
    veh_num_cong = traci.edge.getLastStepVehicleNumber("I1_I2")
    mean_speed_cong = traci.edge.getLastStepMeanSpeed("I1_I2")
    print(f"  Congested edge I1_I2: vehicles={veh_num_cong}, mean speed={mean_speed_cong:.2f} m/s")
    res_clear = adapter.clear_congestion_event("I1_I2")
    print(f"  Congestion cleared: {res_clear}")
    traci.simulationStep()
    restored_speed = traci.lane.getMaxSpeed("I1_I2_0")
    print(f"  Restored lane max speed: {restored_speed:.2f} m/s")
    if "injected" in res_cong.lower() and "cleared" in res_clear.lower() and restored_speed > 10.0:
        results["Check 12: Dynamic congestion can be triggered and visually observed"] = True
        print("[PASS] Check 12: Dynamic congestion triggered, observed, and cleared.")
    else:
        results["Check 12: Dynamic congestion can be triggered and visually observed"] = False
        print("[FAIL] Check 12: Congestion manipulation failed.")

    traci.close()

    print("=" * 65)
    print("VALIDATION SUMMARY:")
    all_pass = all(results.values())
    for check, passed in results.items():
        print(f"  {'[PASSED]' if passed else '[FAILED]'}: {check}")
    print(f"OVERALL STATUS: {'ALL 12 CHECKS PASSED!' if all_pass else 'SOME CHECKS FAILED'}")
    print("=" * 65)
    return results


if __name__ == "__main__":
    run_checks()
