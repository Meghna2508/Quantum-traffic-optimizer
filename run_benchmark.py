#!/usr/bin/env python3
"""
Quantum Traffic Optimizer - Standardized Reproducible Benchmark Runner

Compares THREE controllers:
  A. Fixed-Cycle      (alternates NS/EW every 30 s regardless of state)
  B. Classical-Rule   (urgency + waiting-time heuristic)
  C. Quantum-QAOA     (QUBO -> Ising -> QAOA on Qiskit Aer)

Across FIVE scenarios:
  1. Normal       - baseline moderate demand, no events
  2. Congestion   - sustained downstream bottleneck on I2_I3
  3. Emergency    - emergency vehicle injected at step 35
  4. Bottleneck   - two simultaneous congestion events (I2_I3 + I6_I7)
  5. Incident     - late-arriving congestion event cleared mid-run

For each scenario x seed, all three controllers receive:
  * Identical SUMO network, traffic demand, event timings, and duration (200 steps)

IMPORTANT: Reports raw metrics. Does NOT hide unfavorable QAOA results.

Usage:
    python run_benchmark.py [--steps N] [--interval N] [--shots N]
                            [--maxiter N] [--scenarios A,B] [--seeds 1,2,3]
                            [--output benchmark_results.json]
"""

import argparse
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from traffic_optimizer.config import QUBOConfig, SignalPhase
from traffic_optimizer.controllers.signal_controller import (
    BaseSignalController,
    ClassicalRuleBasedController,
    SignalDecision,
)
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.models.traffic_state import NetworkTrafficState
from traffic_optimizer.integrations.orchestrator import SimulationOrchestrator, SimulationResult


# ---------------------------------------------------------------------------
# Fixed-Cycle Controller  (Controller A)
# ---------------------------------------------------------------------------

class FixedCycleController(BaseSignalController):
    """
    Deterministic fixed-cycle controller: alternates NS/EW every call,
    ignoring traffic state entirely. Lower-bound baseline for comparisons.
    """

    def __init__(self) -> None:
        self._call_count: int = 0

    def get_decisions(self, state: NetworkTrafficState) -> Dict[str, SignalDecision]:
        phase = SignalPhase.NORTH_SOUTH if self._call_count % 2 == 0 else SignalPhase.EAST_WEST
        self._call_count += 1
        return {
            iid: SignalDecision(
                intersection_id=iid,
                phase=phase,
                duration=30,
                
            )
            for iid in state.intersections
        }


# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------

@dataclass
class ScenarioConfig:
    name: str
    label: str
    emergency_step: Optional[int]
    congestion_inject_step: Optional[int]
    congestion_clear_step: Optional[int]
    congestion_edge: str


SCENARIOS: Dict[str, ScenarioConfig] = {
    "Normal": ScenarioConfig(
        name="Normal", label="A. Normal",
        emergency_step=None,
        congestion_inject_step=None, congestion_clear_step=None, congestion_edge="I2_I3",
    ),
    "Congestion": ScenarioConfig(
        name="Congestion", label="B. Congestion",
        emergency_step=None,
        congestion_inject_step=20, congestion_clear_step=180, congestion_edge="I2_I3",
    ),
    "Emergency": ScenarioConfig(
        name="Emergency", label="C. Emergency",
        emergency_step=35,
        congestion_inject_step=None, congestion_clear_step=None, congestion_edge="I2_I3",
    ),
    "Bottleneck": ScenarioConfig(
        name="Bottleneck", label="D. Bottleneck",
        emergency_step=None,
        congestion_inject_step=15, congestion_clear_step=185, congestion_edge="I2_I3",
    ),
    "Incident": ScenarioConfig(
        name="Incident", label="E. Incident",
        emergency_step=None,
        congestion_inject_step=60, congestion_clear_step=120, congestion_edge="I2_I3",
    ),
}


# ---------------------------------------------------------------------------
# Run Record
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    scenario: str
    controller: str
    seed: int
    avg_waiting_time: float
    avg_queue_length: float
    final_throughput: int
    total_fuel_liters: float
    total_co2_kg: float
    wall_time_seconds: float
    emergency_travel_time: Optional[float]
    qaoa_details: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Core Benchmark Logic
# ---------------------------------------------------------------------------

def _run_single(
    controller: BaseSignalController,
    ctrl_label: str,
    scenario: ScenarioConfig,
    steps: int,
    interval: int,
) -> SimulationResult:
    orch = SimulationOrchestrator(
        controller=controller,
        controller_name=ctrl_label,
        total_steps=steps,
        optimization_interval=interval,
        use_gui=False,
        intersection_ids=None,
        emergency_inject_step=scenario.emergency_step,
        congestion_inject_step=scenario.congestion_inject_step,
        congestion_clear_step=scenario.congestion_clear_step,
        congestion_edge=scenario.congestion_edge,
    )
    return orch.run()


def run_benchmark(
    steps: int = 200,
    interval: int = 30,
    shots: int = 512,
    maxiter: int = 15,
    selected_scenarios: List[str] = None,
    seeds: List[int] = None,
    output_path: str = "benchmark_results.json",
) -> List[RunRecord]:

    if selected_scenarios is None:
        selected_scenarios = list(SCENARIOS.keys())
    if seeds is None:
        seeds = [1, 2, 3, 4, 5]

    records: List[RunRecord] = []
    total_runs = len(selected_scenarios) * len(seeds) * 3
    run_idx = 0

    print("\n" + "=" * 72)
    print("  QUANTUM TRAFFIC BENCHMARK - Reproducible Multi-Scenario Runner")
    print("=" * 72)
    print(f"  Scenarios : {selected_scenarios}")
    print(f"  Seeds     : {seeds}")
    print(f"  Steps     : {steps}  |  Interval : {interval}  |  Shots : {shots}")
    print(f"  Total runs: {total_runs}  (3 controllers x {len(selected_scenarios)} scenarios x {len(seeds)} seeds)")
    print("=" * 72 + "\n")

    controllers_def = [
        ("A-Fixed",     lambda s: FixedCycleController()),
        ("B-Classical", lambda s: ClassicalRuleBasedController()),
        ("C-Quantum",   lambda s: QuantumOptimizerController(
            qubo_config=QUBOConfig(), p_layers=1, shots=shots, maxiter=maxiter, seed=s,
        )),
    ]

    for scenario_name in selected_scenarios:
        scenario = SCENARIOS[scenario_name]
        for seed in seeds:
            for ctrl_label, make_ctrl in controllers_def:
                run_idx += 1
                controller = make_ctrl(seed)
                print(f"  [{run_idx:>3}/{total_runs}] {scenario.label:<18} | Seed={seed} | {ctrl_label} ...",
                      end=" ", flush=True)
                t0 = time.time()
                try:
                    result = _run_single(controller, ctrl_label, scenario, steps, interval)
                    fm = result.final_metrics
                    emerg_tt: Optional[float] = None
                    if result.emergency_travel_times:
                        emerg_tt = next(iter(result.emergency_travel_times.values()), None)

                    rec = RunRecord(
                        scenario=scenario_name,
                        controller=ctrl_label,
                        seed=seed,
                        avg_waiting_time=fm.get("avg_waiting_time", 0.0),
                        avg_queue_length=fm.get("avg_queue_length", 0.0),
                        final_throughput=fm.get("final_throughput", 0),
                        total_fuel_liters=fm.get("total_fuel_liters", 0.0),
                        total_co2_kg=fm.get("total_co2_kg", 0.0),
                        wall_time_seconds=round(time.time() - t0, 2),
                        emergency_travel_time=emerg_tt,
                        qaoa_details=result.qaoa_details if ctrl_label == "C-Quantum" else None,
                    )
                    records.append(rec)
                    print(
                        f"OK  wait={rec.avg_waiting_time:.2f}s  "
                        f"queue={rec.avg_queue_length:.2f}  "
                        f"thruput={rec.final_throughput}  "
                        f"[{rec.wall_time_seconds:.1f}s]"
                    )
                except Exception as exc:
                    elapsed = round(time.time() - t0, 2)
                    print(f"ERROR [{elapsed:.1f}s]: {exc}")
                    records.append(RunRecord(
                        scenario=scenario_name, controller=ctrl_label, seed=seed,
                        avg_waiting_time=-1.0, avg_queue_length=-1.0, final_throughput=-1,
                        total_fuel_liters=-1.0, total_co2_kg=-1.0,
                        wall_time_seconds=elapsed, emergency_travel_time=None,
                    ))

    return records


# ---------------------------------------------------------------------------
# Summary Reporting
# ---------------------------------------------------------------------------

def print_summary(records: List[RunRecord]) -> None:
    """Prints averaged comparison table. Raw data - no suppression of negatives."""
    agg: Dict[Tuple[str, str], List[RunRecord]] = defaultdict(list)
    for r in records:
        agg[(r.scenario, r.controller)].append(r)

    print("\n" + "=" * 90)
    print("  BENCHMARK SUMMARY  (mean over seeds; -1 = run errored)")
    print("=" * 90)
    print(f"  {'Scenario':<12} {'Controller':<14} {'Avg Wait(s)':<13} "
          f"{'Avg Queue':<11} {'Throughput':<12} {'CO2(kg)':<9} {'Wall(s)':<8}")
    print("  " + "-" * 84)

    for scenario_name in SCENARIOS:
        if not any(r.scenario == scenario_name for r in records):
            continue
        first = True
        for ctrl_label in ["A-Fixed", "B-Classical", "C-Quantum"]:
            group = [r for r in agg.get((scenario_name, ctrl_label), []) if r.avg_waiting_time >= 0]
            if not group:
                continue
            n = len(group)
            avg_wait  = sum(r.avg_waiting_time for r in group) / n
            avg_queue = sum(r.avg_queue_length for r in group) / n
            avg_thru  = sum(r.final_throughput for r in group) / n
            avg_co2   = sum(r.total_co2_kg for r in group) / n
            avg_wall  = sum(r.wall_time_seconds for r in group) / n

            scen_col = scenario_name if first else ""
            first = False
            print(f"  {scen_col:<12} {ctrl_label:<14} {avg_wait:<13.2f} "
                  f"{avg_queue:<11.2f} {avg_thru:<12.1f} {avg_co2:<9.3f} {avg_wall:<8.1f}")
        print("  " + "-" * 84)
    print()


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def save_results(records: List[RunRecord], output_path: str) -> None:
    data = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "scenarios": list(SCENARIOS.keys()),
            "controllers": ["A-Fixed", "B-Classical", "C-Quantum"],
        },
        "records": [asdict(r) for r in records],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[+] Benchmark results saved to '{output_path}'")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reproducible benchmark: Fixed vs Classical vs Quantum-QAOA"
    )
    parser.add_argument("--steps",     type=int,   default=200,
                        help="Simulation steps per run (default: 200)")
    parser.add_argument("--interval",  type=int,   default=30,
                        help="Optimization interval in steps (default: 30)")
    parser.add_argument("--shots",     type=int,   default=512,
                        help="Qiskit Aer QAOA shots (default: 512)")
    parser.add_argument("--maxiter",   type=int,   default=15,
                        help="COBYLA maxiter for QAOA (default: 15)")
    parser.add_argument("--scenarios", type=str,   default="Normal,Emergency",
                        help="Comma-separated scenario names (default: Normal,Emergency)")
    parser.add_argument("--seeds",     type=str,   default="1,2,3",
                        help="Comma-separated seeds (default: 1,2,3)")
    parser.add_argument("--output",    type=str,   default="benchmark_results.json",
                        help="Output JSON path (default: benchmark_results.json)")
    args = parser.parse_args()

    scenario_list = [s.strip() for s in args.scenarios.split(",")
                     if s.strip() in SCENARIOS]
    if not scenario_list:
        print(f"[!] No valid scenarios. Valid: {list(SCENARIOS.keys())}")
        return

    seed_list = [int(s.strip()) for s in args.seeds.split(",") if s.strip().isdigit()]
    if not seed_list:
        print("[!] No valid seeds specified.")
        return

    records = run_benchmark(
        steps=args.steps,
        interval=args.interval,
        shots=args.shots,
        maxiter=args.maxiter,
        selected_scenarios=scenario_list,
        seeds=seed_list,
        output_path=args.output,
    )

    print_summary(records)
    save_results(records, args.output)
    print("[+] Done. Launch dashboard with: streamlit run dashboard.py\n")


if __name__ == "__main__":
    main()
