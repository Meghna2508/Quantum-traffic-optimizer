# Quantum Traffic Optimizer 🚦⚛️

A quantum-enhanced adaptive urban traffic signal optimization system utilizing QAOA (Quantum Approximate Optimization Algorithm) and QUBO (Quadratic Unconstrained Binary Optimization) coupled with SUMO (Simulation of Urban MObility).

---

## 🌟 Key Features

1. **Microscopic Traffic Simulation with SUMO**:
   - Realistic 2x2 multi-intersection urban grid with bidirectional multilane arterials.
   - TraCI integration (`SUMOAdapter` & `SimulationOrchestrator`) with automated fallback simulator for headless testing.
   - Real-time vehicle tracking, waiting times, queue lengths, and throughput calculation.

2. **Network-Aware QUBO & Ising Formulation**:
   - **Queue Pressure Minimization**: Penalizes long standing queues across North-South and East-West corridors.
   - **Emergency Green Waves**: Prioritizes emergency vehicles (ambulances/fire engines) with immediate preemption and green corridor routing.
   - **Network Coordination (Green Wave Coupling)**: Rewards synchronized green phases between adjacent intersections along primary traffic corridors.
   - **Phase Switching Stability**: Adds inertia penalties to prevent excessive switching and maintain traffic momentum.
   - Exact mathematical conversion between binary variables $x_i \in \{0, 1\}$ and Pauli-$Z$ spins $\sigma_z \in \{-1, +1\}$.

3. **QAOA Quantum Optimization Engine**:
   - Parameterized quantum circuits evaluated on Qiskit Aer Statevector and QASM simulators with COBYLA classical optimization.
   - Optimal phase and green duration selection ($15\text{s}, 30\text{s}, 45\text{s}$) across all network intersections.
   - Probability distribution visualization and bitstring convergence tracking.

4. **Dual Controller Benchmarking**:
   - **Quantum Controller (`QuantumOptimizerController`)**: Evaluates real-time network states, compiles dynamic QUBO/Ising models, solves via QAOA, and actuates traffic lights.
   - **Classical Controller (`ClassicalRuleBasedController`)**: Baseline rule-based controller for rigorous comparative benchmarking.

5. **Interactive Streamlit Dashboard (`dashboard.py`)**:
   - **Benchmark Comparison**: Side-by-side performance comparison of classical vs. QAOA optimization (delay, queue length, throughput, emergency clearance).
   - **QAOA & QUBO Deep Dive**: Cost matrix visualization, Pauli-$Z$ Hamiltonian inspection, parameter convergence ($\gamma, \beta$), and measurement state probabilities.
   - **Live Network Topology**: Visual 2x2 grid representing intersections I1–I4, active phases, queue pressures, and emergency vehicle corridors.
   - **Detailed Benchmark Results**: Tabular and graphical breakdowns across time steps.

---

## 📁 Repository Structure

```
├── dashboard.py                        # Streamlit interactive visualization dashboard
├── demo_results.json                   # Precomputed benchmark comparison data
├── main.py                             # CLI simulation entrypoint
├── quantum_demo.py                     # Standalone QAOA & QUBO demonstration
├── run_benchmark.py                    # Benchmark runner comparing Classical vs. QAOA
├── run_hackathon_demo.py               # Live demo script with SUMO TraCI integration
├── sumo/                               # SUMO simulation files (nodes, edges, routes, cfg)
│   ├── network.nod.xml
│   ├── network.edg.xml
│   ├── network.net.xml
│   ├── routes.rou.xml
│   └── simulation.sumocfg
└── traffic_optimizer/
    ├── config.py                       # Network settings, phases, and cost constants
    ├── controllers/
    │   ├── signal_controller.py        # Classical rule-based controller
    │   └── quantum_controller.py       # QAOA quantum optimizer controller
    ├── integrations/
    │   ├── sumo_adapter.py             # TraCI connector and traffic light controller
    │   └── orchestrator.py             # Event injection, emergency corridor manager
    ├── models/
    │   ├── intersection.py             # Intersection model & signal phase states
    │   ├── road.py                     # Road segment & queue model
    │   └── traffic_state.py            # Global network state snapshot
    ├── network/
    │   └── traffic_network.py          # Network topology and grid builder
    ├── optimization/
    │   ├── cost_model.py               # Objective weights & parameter tuning
    │   └── qubo.py                     # QUBO matrix formulation
    ├── quantum/
    │   ├── ising_converter.py          # QUBO to Ising spin Hamiltonian converter
    │   ├── qaoa_solver.py              # Qiskit QAOA circuit builder & optimizer
    │   └── result.py                   # QAOA execution result dataclass
    ├── simulation/
    │   └── traffic_simulator.py        # Internal traffic simulation engine
    └── tests/                          # Comprehensive pytest test suite (38 tests)
```

---

## 🚀 Quick Start

### 1. Installation

Clone repository and install dependencies:
```bash
git clone https://github.com/Meghna2508/Quantum-traffic-optimizer.git
cd Quantum-traffic-optimizer
git checkout quantum-optimization
pip install -r requirements.txt  # or install qiskit qiskit-aer streamlit traci pytest
```

### 2. Run Tests
```bash
pytest
```
All 38 unit and integration tests validate network state snapshots, QUBO generation, Ising mapping, QAOA convergence, and SUMO TraCI adapters.

### 3. Launch Dashboard
```bash
streamlit run dashboard.py
```
View the live dashboard at `http://localhost:8501`.

### 4. Run Hackathon Demo
```bash
python run_hackathon_demo.py
```

---

## 📊 Benchmark Results

| Metric | Classical Rule-Based | QAOA Quantum Optimization | Relative Improvement |
| :--- | :---: | :---: | :---: |
| **Average Delay per Vehicle** | 18.42s | 13.67s | **-25.8%** |
| **Max Network Queue Length** | 42 vehicles | 26 vehicles | **-38.1%** |
| **Throughput (Vehicles Cleared)** | 312 veh/hr | 389 veh/hr | **+24.7%** |
| **Emergency Corridor Clearance Time**| 35.0s | 18.2s | **-48.0%** |