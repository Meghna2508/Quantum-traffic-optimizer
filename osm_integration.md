# OpenStreetMap (OSM) to SUMO Integration Guide

**Branch**: `final-integration`  
**Scenario Path**: `sumo/osm/`  
**Network Geographic Area**: Midtown Manhattan, New York City (5th Ave, Madison Ave, Park Ave between E 33rd & E 36th St)  
**Date**: 2026-09-20  

---

## 1. Overview & Architecture

The OpenStreetMap (OSM) integration introduces a real-world, GPS-projected urban arterial network into the Quantum Green Corridor project without altering or destabilizing the existing synthetic 2x2 regression fixture (`sumo/simulation.sumocfg`).

The optimizer interface remains entirely decoupled from road geometry:
```
OpenStreetMap (.osm XML)
      ↓
SUMO netconvert (WGS84 UTM 18N)
      ↓
Road Network (.net.xml)
      ↓
Traffic Demand & Emergency Routes (.rou.xml)
      ↓
SUMO / TraCI Simulation Adapter
      ↓
NetworkTrafficState Snapshot (Junctions, Queues, Densities)
      ↓
Signal Controllers (Fixed-Cycle / Classical / Quantum-QAOA)
```

---

## 2. Source Data & Tooling Verification

### A. SUMO Tooling Availability
- `netconvert.exe`: Available on PATH (`C:\Users\harikrishhhh\AppData\Local\Programs\Python\Python311\Scripts\netconvert.exe`).
  - Version: Eclipse SUMO netconvert 1.27.1
  - Features: Proj (WGS84 projection engine), GDAL, GUI, SWIG, FMT.
- Native SUMO tools were utilized directly, eliminating the need for unverified third-party OSM python packages.

### B. Geographic Source Area
- **Location**: Midtown Manhattan, New York, NY
- **Bounding Box**:
  - South: `40.7470° N`
  - West: `-73.9860° W`
  - North: `40.7515° N`
  - East: `-73.9800° W`
- **Acquisition Workflow**: Ingested via OpenStreetMap Overpass API (`interpreter`) filtering for arterial highway types (`primary`, `secondary`, `tertiary`, `residential`). Saved to `sumo/osm/manhattan.osm` (105,485 bytes).

---

## 3. OSM to SUMO Conversion Process

The network was compiled using SUMO's native `netconvert` utility:
```bash
netconvert \
    --osm-files sumo/osm/manhattan.osm \
    -o sumo/osm/manhattan.net.xml \
    --geometry.remove \
    --roundabouts.guess \
    --ramps.guess \
    --junctions.join \
    --tls.guess \
    --tls.discard-simple \
    --tls.join \
    --no-warnings
```

### Conversion Artifacts & Parameters
- **Coordinate Projection**: UTM Zone 18N (`+proj=utm +zone=18 +ellps=WGS84 +datum=WGS84 +units=m +no_defs`).
- **Network Dimensions**:
  - Local Cartesian Bounds: `convBoundary="0.00,0.00,797.53,715.34"` (meters).
  - Original GPS Bounds: `origBoundary="-73.988193,40.746394,-73.978707,40.752887"`.
  - Total Junction Nodes: 48 nodes.
  - Total Roadway Edges: 68 edges.
  - Controlled Signalized Intersections: **18 Traffic Lights** (5 major multi-incoming arterial junctions).

---

## 4. Signalized Intersections & Phasing

All signalized junctions have complete static multi-phase logic defined in `manhattan.net.xml`:
- **Phase 0**: Green for dominant arterial movement (42 s duration).
- **Phase 1**: Yellow transition clearance (3 s duration).
- **Phase 2**: Green for cross-street movement (42 s duration).
- **Phase 3**: Yellow transition clearance (3 s duration).

Major Arterial Junctions:
1. `cluster_3786901743_561042190` (4 incoming arterials)
2. `42445365` (3 incoming arterials)
3. `42437644` (3 incoming arterials)
4. `cluster_12181374928_42434951_561042191` (3 incoming arterials)
5. `cluster_12181374934_42458333_561042193` (3 incoming arterials)

---

## 5. Traffic Demand & Emergency Route Definition

Defined in `sumo/osm/manhattan.rou.xml`:
- **Vehicle Types**:
  - `car`: Standard passenger vehicle (length: 5.0 m, maxSpeed: 13.89 m/s).
  - `truck`: Heavy transport vehicle (length: 8.5 m, maxSpeed: 10.0 m/s).
  - `emergency`: Emergency response vehicle (length: 6.5 m, maxSpeed: 25.0 m/s, speedFactor: 1.5, color: red).
- **Background Traffic**: Continuous Poisson-distributed vehicle insertion on 6 crossing and arterial routes (`R_main1`, `R_main2`, `R_cross1`, `R_cross2`, `R_opposing`, `R_avenue`).
- **Emergency Corridor Route (`R_emergency`)**:
  - Edges: `420904658#0 -> 542096279#0 -> 1201643837#0 -> 458166894#0 -> 420499931#0 -> 420904660#0`
  - Traverses 6 consecutive signalized intersections along the main east-west arterial corridor.

---

## 6. How to Run the OSM Simulation Scenario

### A. Headless SUMO Execution
```bash
sumo -c sumo/osm/simulation_osm.sumocfg --step-length 1 -e 100
```

### B. Python API Execution (Classical & Quantum QAOA)
Run the following script to execute a 60-step closed-loop simulation on the OSM network:
```python
from traffic_optimizer.integrations.orchestrator import SimulationOrchestrator
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.config import QUBOConfig

controller = QuantumOptimizerController(
    qubo_config=QUBOConfig(),
    p_layers=1,
    shots=256,
    maxiter=10,
    seed=42,
)

orchestrator = SimulationOrchestrator(
    controller=controller,
    controller_name="Quantum-OSM",
    config_path="sumo/osm/simulation_osm.sumocfg",
    total_steps=60,
    optimization_interval=15,
    emergency_inject_step=20,
    emergency_route="R_emergency",
    congestion_inject_step=30,
    congestion_clear_step=50,
    congestion_edge="420904658#0",
)

result = orchestrator.run()
print("Execution wall time:", result.wall_time_seconds)
print("Final metrics:", result.final_metrics)
```

### C. GUI Visualization
Launch SUMO-GUI with the OSM scenario:
```bash
sumo-gui -c sumo/osm/simulation_osm.sumocfg
```

---

## 7. Interactive Dashboard Map Visualization

In the Streamlit dashboard (`dashboard.py`), navigate to **Tab 4: Network Topology**:
- Switch the radio toggle from **Synthetic 2x2 Grid Network** to **OpenStreetMap Real-World Network (Manhattan Midtown)**.
- Renders an interactive Plotly map showing:
  - All 68 road segments in the Manhattan Midtown bounding box.
  - All 18 signalized intersections with junction labels.
  - The designated **Emergency Green Corridor** highlighted in prominent dashed red line along Route `R_emergency`.

---

## 8. Limitations & Future Work

1. **Static Initial Signal Programs**: Netconvert generated initial static 42s/3s cycle programs. The controllers dynamically adjust green phases and durations in real-time.
2. **One-Way Street Restrictions**: Manhattan features multiple one-way avenues and streets. Routes in `manhattan.rou.xml` strictly adhere to legal lane directions.
3. **Simulation vs Hardware Execution**: Real quantum hardware execution would submit the chunked 18-qubit circuits to IBM Quantum / Rigetti backends asynchronously.
