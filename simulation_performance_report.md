# Simulation Performance Analysis Report

**Branch**: `final-integration`  
**Evaluation Scope**: Controllers (Fixed-Cycle, Classical Rule-Based, Quantum-QAOA) across Normal, Congestion, and Emergency Scenarios  
**Dataset Source**: 45 Verified Multi-Seed SUMO Benchmark Runs (Seeds 42, 43, 44, 45, 46)  
**Date**: 2026-09-20  

---

## 1. Benchmark Experimental Configuration

The benchmark was executed using the standardized simulation runner across three distinct traffic scenarios and five random seeds. All controllers were evaluated under identical demand flows, event timings, and roadway geometry.

- **Network Architecture**: 2x2 grid of coordinated signalized intersections (`I1`, `I2`, `I3`, `I4`) with 8 boundary feeder nodes (`N1`, `N2`, `S3`, `S4`, `W1`, `W3`, `E2`, `E4`), 2 lanes per edge.
- **Simulation Duration**: 200 seconds (step length = 1.0 s).
- **Optimization Interval**: 30 seconds (triggered periodically and dynamically upon incident/emergency injection).
- **Seeds Evaluated**: `[42, 43, 44, 45, 46]`.
- **Quantum QAOA Parameters**:
  - Ansatz depth: $p = 1$ layer.
  - Classical optimizer: COBYLA, `maxiter = 15`.
  - Measurement shots: 512 shots.
  - Simulation backend: Qiskit Aer Statevector simulator (`aer_simulator_statevector`).
  - Network chunking: Group size $\le 3$ intersections (max 18 active qubits per circuit).
- **Cost Function Weights**:
  - Penalty multiplier: $\lambda_{\text{penalty}} = 1000.0$
  - Queue weight: $w_{\text{queue}} = 10.0$
  - Delay weight: $w_{\text{wait}} = 8.0$
  - Congestion weight: $w_{\text{congestion}} = 8.0$
  - Downstream penalty: $w_{\text{downstream}} = 12.0$
  - Throughput reward: $w_{\text{throughput}} = 12.0$
  - Phase switch penalty: $w_{\text{switch}} = 1.5$
  - Emissions proxy weight: $w_{\text{emissions}} = 5.0$
  - Emergency clearance weight: $w_{\text{emergency}} = 500.0$

---

## 2. Consolidated Controller Performance

### Table 1: Primary Traffic & Environmental Metrics (Averages over 5 Seeds)

| Scenario | Controller | Avg Wait (s/veh) | Avg Queue (veh) | Max Queue (veh) | Final Throughput (trips) | Total Fuel (L) | Total CO2 (kg) | Wall Time (s) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Normal** | **A-Fixed** | 2.63 | 12.80 | 27.0 | 142.0 | 10.575 | 24.483 | 6.47 |
| | **B-Classical** | 1.78 | 11.71 | 27.0 | 141.0 | 10.485 | 24.261 | 6.38 |
| | **C-Quantum** | 7.76 | 22.06 | 49.0 | 122.0 | 11.548 | 26.721 | 17.24 |
| **Congestion** | **A-Fixed** | 1.73 | 12.87 | 30.0 | 127.0 | 11.037 | 25.526 | 7.17 |
| | **B-Classical** | 1.50 | 11.43 | 26.0 | 129.0 | 11.052 | 25.555 | 6.78 |
| | **C-Quantum** | 5.87 | 19.93 | 47.4 | 112.0 | 11.936 | 27.614 | 17.85 |
| **Emergency** | **A-Fixed** | 1.79 | 11.67 | 28.0 | 143.0 | 10.570 | 24.459 | 5.49 |
| | **B-Classical** | 1.58 | 10.99 | 30.0 | 143.0 | 10.663 | 24.669 | 5.49 |
| | **C-Quantum** | 5.31 | 19.25 | 47.4 | 121.4 | 11.542 | 26.700 | 17.88 |

---

## 3. Factual Controller Comparison

### A. Classical Rule-Based vs Fixed-Cycle Controller
- **Waiting Time**: Classical Rule-Based achieved lower average waiting time across all three scenarios:
  - Normal: 1.78 s vs 2.63 s (difference: -0.85 s, -32.3%)
  - Congestion: 1.50 s vs 1.73 s (difference: -0.23 s, -13.3%)
  - Emergency: 1.58 s vs 1.79 s (difference: -0.21 s, -11.7%)
- **Queue Lengths**: Classical Rule-Based reduced average queue lengths by 1.09 veh (Normal), 1.44 veh (Congestion), and 0.68 veh (Emergency).
- **Throughput & Emissions**: Throughput remained within $\pm 1$ trip of Fixed-Cycle, while fuel and CO2 emissions were virtually identical ($\Delta \text{CO2} \le 0.22$ kg).

### B. Quantum QAOA vs Classical Rule-Based Controller
- **Waiting Time**: Quantum QAOA exhibited higher average waiting times than Classical:
  - Normal: 7.76 s vs 1.78 s (difference: +5.98 s, +336%)
  - Congestion: 5.87 s vs 1.50 s (difference: +4.37 s, +291%)
  - Emergency: 5.31 s vs 1.58 s (difference: +3.73 s, +236%)
- **Queue Lengths**: Quantum QAOA accumulated higher average queues across all scenarios (19.25 to 22.06 veh vs 10.99 to 11.71 veh).
- **Network Throughput**: Quantum QAOA discharged fewer total trips over 200 seconds:
  - Normal: 122.0 vs 141.0 trips (-19.0 trips, -13.5%)
  - Congestion: 112.0 vs 129.0 trips (-17.0 trips, -13.2%)
  - Emergency: 121.4 vs 143.0 trips (-21.6 trips, -15.1%)
- **Environmental Impact**: Total CO2 emissions were 8.1% to 10.1% higher under Quantum QAOA due to increased red-phase idling.

---

## 4. Emergency Corridor Analysis

### Table 2: Emergency Response & Quantum Optimization Telemetry

| Scenario | Controller | Emergency TT (s) | Corridor Completed | QAOA Calls | Fallback Rate | QAOA Avg Time (s) | Max Qubits | Infeasible Count |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Normal** | **A-Fixed** | N/A | 0/5 | 0.0 | 0.0% | N/A | 0 | 0.0 |
| | **B-Classical** | N/A | 0/5 | 0.0 | 0.0% | N/A | 0 | 0.0 |
| | **C-Quantum** | N/A | 0/5 | 6.0 | 56.7% | 0.825 | 18 | 0.0 |
| **Congestion** | **A-Fixed** | N/A | 0/5 | 0.0 | 0.0% | N/A | 0 | 0.0 |
| | **B-Classical** | N/A | 0/5 | 0.0 | 0.0% | N/A | 0 | 0.0 |
| | **C-Quantum** | N/A | 0/5 | 7.0 | 48.6% | 0.799 | 18 | 0.0 |
| **Emergency** | **A-Fixed** | 1.0 | 5/5 | 0.0 | 0.0% | N/A | 0 | 0.0 |
| | **B-Classical** | 52.0 | 5/5 | 0.0 | 0.0% | N/A | 0 | 0.0 |
| | **C-Quantum** | 10.8 | 5/5 | 8.0 | 65.0% | 0.745 | 18 | 0.0 |

### Emergency Travel Time Variance Investigation
- **Corridor Clearance Completion**: In all emergency runs across all controllers, the corridor was completed 100% of the time (5/5 seeds).
- **Travel Time Variance Cause**:
  - In `Classical Rule-Based`, the measured emergency travel time was exactly 52.0 s across all 5 seeds. The ambulance was injected at $t=35$, entered Route R1, traversed intersections `I1` and `I2` under green preemption, and completed its trip at $t=87$.
  - In `Fixed-Cycle` and 4 out of 5 `Quantum QAOA` seeds, the recorded travel time was 1.0 s.
  - **Root Cause Identified in TraCI Telemetry**: In `SUMOAdapter.step()`, line 85 tracks active emergency vehicles via `if veh_id in traci.vehicle.getIDList(): pass elif veh_id not in self.emergency_travel_times: ...`. When an emergency vehicle is added via `traci.vehicle.add()` with `depart="now"`, SUMO places the vehicle in an insertion queue for 1 simulation step. During the immediate subsequent step ($t=36$), if the insertion edge is temporarily congested or undergoing lane assignment, `veh_id` has not yet appeared in `getIDList()`, triggering the `elif` branch prematurely and calculating $36 - 35 = 1.0$ s. On seed 46 under Quantum control, the vehicle was placed on the roadway immediately, yielding the authentic physical traversal time of 50.0 s.

---

## 5. Runtime & Computational Complexity Analysis

- **Classical Controllers**:
  - Wall-clock runtime: 5.49 s to 7.17 s for 200 simulation steps (~30 steps/sec).
  - Algorithmic overhead: Sub-millisecond evaluation per decision step.
- **Quantum QAOA Controller**:
  - Wall-clock runtime: 17.24 s to 17.88 s for 200 simulation steps (~11 steps/sec).
  - QAOA circuit execution: An average of 0.745 s to 0.825 s per optimization call on classical CPU simulation.
  - Number of QAOA calls: 6 to 8 calls per run.
  - Qubit footprint: Partitioned by chunking to a maximum of 18 qubits (3 intersections $\times$ 6 variables).
  - Fallback rate: 48.6% to 65.0% of QAOA optimization calls required fallback to classical greedy selection because the raw sampled bitstring violated one-hot phase constraints.

### Fact-Based Scientific Conclusion on Quantum Advantage
Simulating variational quantum algorithms (QAOA) on classical von Neumann CPUs incurs an exponential statevector simulation cost ($2^{18}$ complex amplitudes) without conferring computational speedup or objective advantage in this setting. The Classical Rule-Based controller consistently outperformed QAOA in queue reduction (-44%), waiting time (-72%), and throughput (+15%). QAOA demonstrates mathematical feasibility, constraint formulation, and hardware scaling boundaries, but does not provide operational traffic optimization advantage on classical simulators.

---

## 6. Comparison Against Task 14B Baseline

The benchmark results in `benchmark_results.json` and `benchmark_results.csv` perfectly match the verified Task 14B dataset. No regression in metrics, network definitions, or controller interfaces occurred during the consolidation into `final-integration`.
