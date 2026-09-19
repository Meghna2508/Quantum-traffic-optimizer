#!/usr/bin/env python3
"""
Quantum-Enhanced Adaptive Urban Traffic Optimization
Hackathon End-to-End Demonstration Script

Executes side-by-side benchmark between:
1. Classical Rule-Based Controller (Demand & Waiting Time Heuristics)
2. Quantum QAOA Controller (QUBO -> Ising -> Aer Simulation -> Feasible Bitstring)

Under dynamic events:
- Emergency vehicle priority routing
- Traffic incident / congestion speed reduction & recovery
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Any, List

import sumolib

from traffic_optimizer.config import QUBOConfig
from traffic_optimizer.controllers.signal_controller import ClassicalRuleBasedController
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.integrations.orchestrator import SimulationOrchestrator, SimulationResult


def print_banner():
    banner = """
================================================================================
     QUANTUM-ENHANCED ADAPTIVE URBAN TRAFFIC OPTIMIZATION
             Hackathon Benchmark & Demonstration Engine
================================================================================
Architecture:
  * Traffic Simulator: SUMO (TraCI) Grid Network
  * Classical Engine : Rule-Based Urgency & Emergency Override Controller
  * Quantum Engine   : QUBO formulation -> Ising Hamiltonian -> QAOA (Qiskit Aer)
================================================================================
"""
    print(banner)


def format_table_row(metric: str, classical_val: str, quantum_val: str, diff_val: str) -> str:
    return f"  | {metric:<32} | {classical_val:>16} | {quantum_val:>16} | {diff_val:>14} |"


def calculate_diff(classical: float, quantum: float, lower_is_better: bool = True) -> str:
    if classical == 0:
        return "N/A"
    pct = ((quantum - classical) / classical) * 100.0
    if lower_is_better:
        # Negative pct means quantum is lower (better)
        if pct < -0.1:
            return f"{abs(pct):.1f}% better"
        elif pct > 0.1:
            return f"{pct:.1f}% higher"
        else:
            return "Parity"
    else:
        # Higher is better
        if pct > 0.1:
            return f"{pct:.1f}% higher"
        elif pct < -0.1:
            return f"{abs(pct):.1f}% lower"
        else:
            return "Parity"


def run_demo(
    steps: int = 100,
    interval: int = 30,
    use_gui: bool = False,
    emergency_step: int = 35,
    congestion_step: int = 50,
    congestion_clear_step: int = 80,
    congestion_edge: str = "I1_I2",
    quantum_intersections: List[str] = None,
    shots: int = 512,
    maxiter: int = 15,
    output_json: str = "demo_results.json",
):
    if quantum_intersections is None:
        # Default 2 intersections for fast yet authentic local QAOA demonstration
        quantum_intersections = ["I1", "I2"]

    print(f"[*] Configuration:")
    print(f"    Total Simulation Steps : {steps}")
    print(f"    Optimization Interval  : {interval} steps")
    print(f"    SUMO GUI Mode          : {use_gui}")
    print(f"    Emergency Step         : {emergency_step} (Route R1)")
    print(f"    Congestion Event       : Steps {congestion_step} - {congestion_clear_step} on edge {congestion_edge}")
    print(f"    Quantum Intersections  : {quantum_intersections} ({len(quantum_intersections)*6} qubits)")
    print(f"    QAOA Config            : p=1, shots={shots}, maxiter={maxiter}")
    print(f"    Output JSON            : {output_json}")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. Classical Rule-Based Run
    # -------------------------------------------------------------------------
    print("\n[PHASE 1/2] Running Classical Rule-Based Controller Simulation...")
    classical_controller = ClassicalRuleBasedController()
    classical_orchestrator = SimulationOrchestrator(
        controller=classical_controller,
        controller_name="Classical-RuleBased",
        total_steps=steps,
        optimization_interval=interval,
        use_gui=use_gui,
        emergency_inject_step=emergency_step,
        congestion_inject_step=congestion_step,
        congestion_clear_step=congestion_clear_step,
        congestion_edge=congestion_edge,
    )

    def classical_progress(s, total):
        if s % 20 == 0 or s == total:
            print(f"    [Classical] Step {s:>3}/{total} completed.")

    classical_result = classical_orchestrator.run(progress_callback=classical_progress)
    print(f"    [Classical] Finished in {classical_result.wall_time_seconds:.2f}s wall time.")

    # -------------------------------------------------------------------------
    # 2. Quantum QAOA Run
    # -------------------------------------------------------------------------
    print("\n[PHASE 2/2] Running Quantum (QAOA) Controller Simulation...")
    quantum_controller = QuantumOptimizerController(
        qubo_config=QUBOConfig(),
        p_layers=1,
        shots=shots,
        maxiter=maxiter,
        seed=42,
    )
    quantum_orchestrator = SimulationOrchestrator(
        controller=quantum_controller,
        controller_name="Quantum-QAOA",
        total_steps=steps,
        optimization_interval=interval,
        use_gui=use_gui,
        intersection_ids=quantum_intersections,
        emergency_inject_step=emergency_step,
        congestion_inject_step=congestion_step,
        congestion_clear_step=congestion_clear_step,
        congestion_edge=congestion_edge,
    )

    def quantum_progress(s, total):
        if s % interval == 0:
            last_res = getattr(quantum_controller, "last_result", None)
            detail_str = ""
            if last_res:
                detail_str = f" | QAOA: cost={last_res.qubo_cost}, t={last_res.execution_time_seconds:.2f}s, feasible={last_res.is_feasible}"
            print(f"    [Quantum] Step {s:>3}/{total} (Optimization triggered{detail_str})")
        elif s % 20 == 0 or s == total:
            print(f"    [Quantum] Step {s:>3}/{total} completed.")

    quantum_result = quantum_orchestrator.run(progress_callback=quantum_progress)
    print(f"    [Quantum] Finished in {quantum_result.wall_time_seconds:.2f}s wall time.")

    # -------------------------------------------------------------------------
    # 3. Side-by-Side Comparison Reporting
    # -------------------------------------------------------------------------
    c_final = classical_result.final_metrics
    q_final = quantum_result.final_metrics

    c_emerg = classical_result.emergency_travel_times.get("emergency_Classical-RuleBased", 0.0)
    q_emerg = quantum_result.emergency_travel_times.get("emergency_Quantum-QAOA", 0.0)

    print("\n" + "=" * 80)
    print("                    BENCHMARK PERFORMANCE COMPARISON")
    print("=" * 80)
    divider = "  +" + "-" * 34 + "+" + "-" * 18 + "+" + "-" * 18 + "+" + "-" * 16 + "+"
    print(divider)
    print(f"  | {'Metric':<32} | {'Classical':>16} | {'Quantum (QAOA)':>16} | {'Comparison':>14} |")
    print(divider)

    print(format_table_row(
        "Avg Waiting Time (s/veh)",
        f"{c_final.get('avg_waiting_time', 0.0):.2f}",
        f"{q_final.get('avg_waiting_time', 0.0):.2f}",
        calculate_diff(c_final.get('avg_waiting_time', 0.0), q_final.get('avg_waiting_time', 0.0), True)
    ))
    print(format_table_row(
        "Avg Queue Length (veh)",
        f"{c_final.get('avg_queue_length', 0.0):.2f}",
        f"{q_final.get('avg_queue_length', 0.0):.2f}",
        calculate_diff(c_final.get('avg_queue_length', 0.0), q_final.get('avg_queue_length', 0.0), True)
    ))
    print(format_table_row(
        "Total Completed Trips",
        f"{c_final.get('final_throughput', 0)}",
        f"{q_final.get('final_throughput', 0)}",
        calculate_diff(float(c_final.get('final_throughput', 0)), float(q_final.get('final_throughput', 0)), False)
    ))
    print(format_table_row(
        "Active Vehicles at End",
        f"{c_final.get('final_vehicle_count', 0)}",
        f"{q_final.get('final_vehicle_count', 0)}",
        calculate_diff(float(c_final.get('final_vehicle_count', 0)), float(q_final.get('final_vehicle_count', 0)), True)
    ))
    print(format_table_row(
        "Fuel Consumption (Liters)",
        f"{c_final.get('total_fuel_liters', 0.0):.3f}",
        f"{q_final.get('total_fuel_liters', 0.0):.3f}",
        calculate_diff(c_final.get('total_fuel_liters', 0.0), q_final.get('total_fuel_liters', 0.0), True)
    ))
    print(format_table_row(
        "CO2 Emissions (kg)",
        f"{c_final.get('total_co2_kg', 0.0):.3f}",
        f"{q_final.get('total_co2_kg', 0.0):.3f}",
        calculate_diff(c_final.get('total_co2_kg', 0.0), q_final.get('total_co2_kg', 0.0), True)
    ))
    if c_emerg > 0 or q_emerg > 0:
        print(format_table_row(
            "Emergency Travel Time (s)",
            f"{c_emerg:.1f}",
            f"{q_emerg:.1f}",
            calculate_diff(c_emerg, q_emerg, True) if c_emerg > 0 and q_emerg > 0 else "N/A"
        ))
    print(format_table_row(
        "Total Wall Time (s)",
        f"{classical_result.wall_time_seconds:.2f}",
        f"{quantum_result.wall_time_seconds:.2f}",
        "N/A"
    ))
    print(divider)

    # QAOA Specific Details
    if quantum_result.qaoa_details:
        q_d = quantum_result.qaoa_details
        print("\n[*] Quantum QAOA Execution Details (Final Optimization):")
        print(f"    Selected Bitstring      : {q_d.get('selected_bitstring')}")
        print(f"    QUBO Objective Value    : {q_d.get('qubo_cost')}")
        print(f"    Constraint Feasible     : {q_d.get('is_feasible')}")
        print(f"    Ansatz Layers (p)       : {q_d.get('p_layers')}")
        print(f"    Optimal Gamma (gamma)   : {q_d.get('optimal_gamma')}")
        print(f"    Optimal Beta (beta)     : {q_d.get('optimal_beta')}")
        print(f"    QAOA Circuit Time       : {q_d.get('execution_time_seconds', 0):.4f}s")
        print(f"    Classical Fallback Used : {q_d.get('is_fallback')}")

    # -------------------------------------------------------------------------
    # 4. Save Results to JSON for Dashboard Replay
    # -------------------------------------------------------------------------
    serializable_output = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "steps": steps,
            "interval": interval,
            "quantum_intersections": quantum_intersections,
        },
        "classical": {
            "final_metrics": c_final,
            "step_metrics": [
                {
                    "step": sm.step,
                    "sim_time": sm.sim_time,
                    "vehicle_count": sm.vehicle_count,
                    "avg_waiting_time": sm.avg_waiting_time,
                    "total_queue": sm.total_queue,
                    "throughput": sm.throughput,
                    "fuel_liters": sm.fuel_consumption_liters,
                    "co2_kg": sm.co2_emissions_kg,
                    "events": sm.events,
                }
                for sm in classical_result.step_metrics
            ],
            "emergency_travel_times": classical_result.emergency_travel_times,
        },
        "quantum": {
            "final_metrics": q_final,
            "step_metrics": [
                {
                    "step": sm.step,
                    "sim_time": sm.sim_time,
                    "vehicle_count": sm.vehicle_count,
                    "avg_waiting_time": sm.avg_waiting_time,
                    "total_queue": sm.total_queue,
                    "throughput": sm.throughput,
                    "fuel_liters": sm.fuel_consumption_liters,
                    "co2_kg": sm.co2_emissions_kg,
                    "events": sm.events,
                }
                for sm in quantum_result.step_metrics
            ],
            "emergency_travel_times": quantum_result.emergency_travel_times,
            "qaoa_details": quantum_result.qaoa_details,
        },
    }

    with open(output_json, "w") as f:
        json.dump(serializable_output, f, indent=2)

    print(f"\n[+] Results saved successfully to '{output_json}'.")
    print("[+] Launch the Streamlit dashboard with: streamlit run dashboard.py\n")


def main():
    parser = argparse.ArgumentParser(
        description="Quantum vs Classical Urban Traffic Optimization Benchmark"
    )
    parser.add_argument("--steps", type=int, default=100, help="Total simulation steps (default: 100)")
    parser.add_argument("--interval", type=int, default=30, help="Optimization interval in steps (default: 30)")
    parser.add_argument("--gui", action="store_true", help="Launch SUMO-GUI instead of headless CLI")
    parser.add_argument("--emergency-step", type=int, default=35, help="Step to inject emergency vehicle (default: 35)")
    parser.add_argument("--congestion-step", type=int, default=50, help="Step to trigger incident congestion (default: 50)")
    parser.add_argument("--congestion-clear-step", type=int, default=80, help="Step to clear incident congestion (default: 80)")
    parser.add_argument("--congestion-edge", type=str, default="I1_I2", help="SUMO edge ID for incident (default: I1_I2)")
    parser.add_argument("--quantum-intersections", type=str, default="I1,I2", help="Comma-separated list of intersections for QAOA (default: I1,I2)")
    parser.add_argument("--shots", type=int, default=512, help="Qiskit Aer shots (default: 512)")
    parser.add_argument("--maxiter", type=int, default=15, help="Classical optimizer iterations for QAOA (default: 15)")
    parser.add_argument("--output", type=str, default="demo_results.json", help="Path to output JSON results file")

    args = parser.parse_args()
    print_banner()

    q_intersections = [x.strip() for x in args.quantum_intersections.split(",") if x.strip()]

    run_demo(
        steps=args.steps,
        interval=args.interval,
        use_gui=args.gui,
        emergency_step=args.emergency_step,
        congestion_step=args.congestion_step,
        congestion_clear_step=args.congestion_clear_step,
        congestion_edge=args.congestion_edge,
        quantum_intersections=q_intersections,
        shots=args.shots,
        maxiter=args.maxiter,
        output_json=args.output,
    )


if __name__ == "__main__":
    main()
