"""
Quantum-Enhanced Adaptive Urban Traffic Optimization
Streamlit Hackathon Dashboard

Features:
- Dual-mode operation: SUMO (TraCI) live execution & Mock Simulation fallback
- Benchmark Comparison: Classical Rule-Based vs Quantum (QAOA) Optimizer
- Real-time KPI cards, time-series curves, and dynamic event markers
- QAOA Deep Dive: Hamiltonian, variational parameters, bitstring probabilities, QUBO costs
- Network Topology visualizer: Intersection phase states, queues, and capacities
"""

import json
import os
import sys
import time
from typing import Dict, Any, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Check local dependencies
try:
    import sumolib
    SUMO_AVAILABLE = True
except Exception:
    SUMO_AVAILABLE = False

from traffic_optimizer.config import SignalPhase, Direction, QUBOConfig
from traffic_optimizer.controllers.signal_controller import (
    ClassicalRuleBasedController,
    SignalDecision,
)
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.models.traffic_state import NetworkTrafficState
from traffic_optimizer.network.traffic_network import TrafficNetwork
from traffic_optimizer.simulation.traffic_simulator import TrafficSimulator

if SUMO_AVAILABLE:
    from traffic_optimizer.integrations.orchestrator import SimulationOrchestrator

# -----------------------------------------------------------------------------
# PAGE CONFIG & CUSTOM THEME
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Quantum Traffic Optimizer",
    page_icon="ðŸš¦",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background: radial-gradient(circle at 10% 20%, #0a0e1a 0%, #030712 100%);
        color: #f3f4f6;
    }
    
    /* Header Gradient Banner */
    .hero-container {
        padding: 1.8rem 2.2rem;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(16, 24, 40, 0.9) 0%, rgba(30, 41, 59, 0.8) 100%);
        border: 1px solid rgba(59, 130, 246, 0.3);
        box-shadow: 0 10px 30px -10px rgba(0, 242, 254, 0.2);
        margin-bottom: 2rem;
    }
    
    .hero-title {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.4rem;
    }
    
    .hero-subtitle {
        color: #94a3b8;
        font-size: 1.05rem;
        max-width: 900px;
        line-height: 1.5;
    }
    
    /* KPI Metric Cards */
    .metric-card {
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(51, 65, 85, 0.8);
        border-radius: 12px;
        padding: 1.2rem 1.4rem;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: rgba(56, 189, 248, 0.6);
    }
    .metric-title {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
        margin-bottom: 0.4rem;
    }
    .metric-value {
        font-size: 1.85rem;
        font-weight: 700;
        color: #f8fafc;
        font-family: 'JetBrains Mono', monospace;
    }
    .metric-diff {
        font-size: 0.85rem;
        font-weight: 600;
        margin-top: 0.3rem;
    }
    .metric-diff.positive { color: #34d399; }
    .metric-diff.negative { color: #f87171; }
    .metric-diff.neutral { color: #94a3b8; }
    
    /* Quantum Badge */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-quantum {
        background: rgba(129, 140, 248, 0.2);
        color: #a5b4fc;
        border: 1px solid rgba(129, 140, 248, 0.4);
    }
    .badge-sumo {
        background: rgba(52, 211, 153, 0.2);
        color: #6ee7b7;
        border: 1px solid rgba(52, 211, 153, 0.4);
    }
    .badge-mock {
        background: rgba(251, 191, 36, 0.2);
        color: #fcd34d;
        border: 1px solid rgba(251, 191, 36, 0.4);
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# HELPER DATA LOADERS
# -----------------------------------------------------------------------------
@st.cache_data
def load_saved_results(filepath: str = "demo_results.json") -> Optional[Dict[str, Any]]:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


@st.cache_data
def load_benchmark_results(filepath: str = "benchmark_results.json") -> Optional[Dict[str, Any]]:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


# -----------------------------------------------------------------------------
# SIDEBAR
# -----------------------------------------------------------------------------
st.sidebar.markdown("## ðŸš¦ Optimizer Controls")

mode_options = ["Saved Benchmark", "Mock Simulation Engine"]
if SUMO_AVAILABLE:
    mode_options.insert(1, "Live SUMO Simulation")

selected_mode = st.sidebar.radio("Execution Mode", mode_options)

st.sidebar.markdown("---")
st.sidebar.markdown("### âš›ï¸ Quantum QAOA Settings")
qaoa_p = st.sidebar.slider("Ansatz Layers (p)", min_value=1, max_value=3, value=1)
qaoa_shots = st.sidebar.select_slider("Aer Simulator Shots", options=[128, 256, 512, 1024], value=256)
qaoa_maxiter = st.sidebar.slider("Classical Optimizer Maxiter", min_value=5, max_value=30, value=10)

st.sidebar.markdown("---")
st.sidebar.markdown("### ðŸš¨ Dynamic Event Triggers")
enable_emergency = st.sidebar.checkbox("Emergency Priority Routing", value=True)
enable_congestion = st.sidebar.checkbox("Incident / Congestion Event", value=True)

st.sidebar.markdown("---")
if SUMO_AVAILABLE:
    st.sidebar.markdown('<span class="badge badge-sumo">SUMO Engine Detected</span>', unsafe_allow_html=True)
else:
    st.sidebar.markdown('<span class="badge badge-mock">Standalone Mock Engine</span>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# HEADER HERO SECTION
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero-container">
        <div class="hero-title">Quantum-Enhanced Adaptive Urban Traffic Optimization</div>
        <div class="hero-subtitle">
            Hybrid Quantum-Classical architecture orchestrating urban signal timing via 
            <b>QUBO Formulation</b> and <b>QAOA (Quantum Approximate Optimization Algorithm)</b> 
            evaluated on TraCI SUMO micro-simulation and mock urban grids.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# TABS
# -----------------------------------------------------------------------------
tab_comparison, tab_live, tab_qaoa, tab_network, tab_benchmark = st.tabs([
    "ðŸ“Š Benchmark Comparison",
    "ðŸš€ Live Simulation Run",
    "âš›ï¸ QAOA & QUBO Deep Dive",
    "ðŸ—ºï¸ Network Topology",
    "ðŸ”¬ Benchmark Results",
])


# =============================================================================
# TAB 1: BENCHMARK COMPARISON
# =============================================================================
with tab_comparison:
    data = load_saved_results("demo_results.json")

    if data is None:
        st.info("â„¹ï¸ No saved benchmark results found. Run `python run_hackathon_demo.py` or trigger a live simulation in the Live Run tab.")
    else:
        c_final = data["classical"]["final_metrics"]
        q_final = data["quantum"]["final_metrics"]

        # KPI Row
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            c_val = c_final.get("avg_waiting_time", 0.0)
            q_val = q_final.get("avg_waiting_time", 0.0)
            diff_pct = ((q_val - c_val) / c_val * 100.0) if c_val > 0 else 0.0
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">Avg Waiting Time</div>
                    <div class="metric-value">{q_val:.2f} s</div>
                    <div class="metric-diff {'positive' if diff_pct <= 0 else 'negative'}">
                        {abs(diff_pct):.1f}% {'lower vs classical' if diff_pct <= 0 else 'higher vs classical'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            c_queue = c_final.get("avg_queue_length", 0.0)
            q_queue = q_final.get("avg_queue_length", 0.0)
            q_diff = ((q_queue - c_queue) / c_queue * 100.0) if c_queue > 0 else 0.0
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">Avg Queue Length</div>
                    <div class="metric-value">{q_queue:.2f} veh</div>
                    <div class="metric-diff {'positive' if q_diff <= 0 else 'negative'}">
                        {abs(q_diff):.1f}% {'queue reduction' if q_diff <= 0 else 'increase'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col3:
            c_tp = c_final.get("final_throughput", 0)
            q_tp = q_final.get("final_throughput", 0)
            tp_diff = ((q_tp - c_tp) / c_tp * 100.0) if c_tp > 0 else 0.0
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">Completed Trips</div>
                    <div class="metric-value">{q_tp}</div>
                    <div class="metric-diff {'positive' if tp_diff >= 0 else 'negative'}">
                        {abs(tp_diff):.1f}% {'higher throughput' if tp_diff >= 0 else 'lower'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col4:
            q_co2 = q_final.get("total_co2_kg", 0.0)
            c_co2 = c_final.get("total_co2_kg", 0.0)
            co2_diff = ((q_co2 - c_co2) / c_co2 * 100.0) if c_co2 > 0 else 0.0
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">CO2 Emissions</div>
                    <div class="metric-value">{q_co2:.2f} kg</div>
                    <div class="metric-diff {'positive' if co2_diff <= 0 else 'neutral'}">
                        Classical: {c_co2:.2f} kg
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # Timeseries Charts
        c_steps = pd.DataFrame(data["classical"]["step_metrics"])
        q_steps = pd.DataFrame(data["quantum"]["step_metrics"])

        fig_cols = st.columns(2)

        with fig_cols[0]:
            fig_queue = go.Figure()
            fig_queue.add_trace(go.Scatter(
                x=c_steps["step"], y=c_steps["total_queue"],
                mode="lines", name="Classical Controller",
                line=dict(color="#f59e0b", width=2, dash="dot"),
            ))
            fig_queue.add_trace(go.Scatter(
                x=q_steps["step"], y=q_steps["total_queue"],
                mode="lines", name="Quantum (QAOA)",
                line=dict(color="#38bdf8", width=2.5),
            ))
            fig_queue.update_layout(
                title="<b>Network Total Queue Length over Time</b>",
                template="plotly_dark",
                paper_bgcolor="rgba(15,23,42,0.6)",
                plot_bgcolor="rgba(15,23,42,0.3)",
                xaxis_title="Simulation Step (seconds)",
                yaxis_title="Vehicles in Queue",
                margin=dict(l=40, r=20, t=50, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_queue, width='stretch')

        with fig_cols[1]:
            fig_wait = go.Figure()
            fig_wait.add_trace(go.Scatter(
                x=c_steps["step"], y=c_steps["avg_waiting_time"],
                mode="lines", name="Classical Controller",
                line=dict(color="#f59e0b", width=2, dash="dot"),
            ))
            fig_wait.add_trace(go.Scatter(
                x=q_steps["step"], y=q_steps["avg_waiting_time"],
                mode="lines", name="Quantum (QAOA)",
                line=dict(color="#818cf8", width=2.5),
            ))
            fig_wait.update_layout(
                title="<b>Average Vehicle Waiting Time over Time</b>",
                template="plotly_dark",
                paper_bgcolor="rgba(15,23,42,0.6)",
                plot_bgcolor="rgba(15,23,42,0.3)",
                xaxis_title="Simulation Step (seconds)",
                yaxis_title="Avg Waiting Time (seconds)",
                margin=dict(l=40, r=20, t=50, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_wait, width='stretch')


# =============================================================================
# TAB 2: LIVE SIMULATION RUN
# =============================================================================
with tab_live:
    st.markdown("### Interactive Simulation Execution")
    st.write("Trigger an ad-hoc run comparing Classical and Quantum controllers with real-time parameter feedback.")

    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns(3)
    with ctrl_col1:
        run_steps = st.number_input("Total Simulation Steps", min_value=10, max_value=200, value=40, step=10)
    with ctrl_col2:
        run_interval = st.number_input("Optimization Interval", min_value=5, max_value=60, value=20, step=5)
    with ctrl_col3:
        target_intersections = st.multiselect(
            "Quantum-Optimized Intersections",
            options=["I1", "I2", "I3", "I4"],
            default=["I1", "I2"],
            help="Each intersection introduces 6 qubits into the QAOA ansatz."
        )

    if st.button("ðŸš€ Launch Live Comparison", type="primary"):
        if not SUMO_AVAILABLE:
            st.warning("SUMO engine not detected. Executing in Mock Simulation mode.")
            # Run mock simulation
            net = TrafficNetwork.create_grid_network(num_intersections=4)
            sim = TrafficSimulator(net, random_seed=42)
            ctrl = ClassicalRuleBasedController()
            with st.spinner("Simulating traffic in Mock Mode..."):
                for _ in range(run_steps):
                    sim.step(controller=ctrl)
                st.success(f"Mock simulation finished for {run_steps} steps!")
                state = net.get_network_state()
                st.write("Final Intersection Queues:", {iid: s.queue_lengths for iid, s in state.intersections.items()})
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                # 1. Classical Run
                status_text.markdown("â³ Running Classical Rule-Based Controller...")
                c_ctrl = ClassicalRuleBasedController()
                c_orch = SimulationOrchestrator(
                    controller=c_ctrl,
                    controller_name="Classical-Live",
                    total_steps=run_steps,
                    optimization_interval=run_interval,
                    emergency_inject_step=run_steps // 2 if enable_emergency else None,
                    congestion_inject_step=int(run_steps * 0.6) if enable_congestion else None,
                    congestion_clear_step=int(run_steps * 0.85) if enable_congestion else None,
                )
                c_res = c_orch.run()

                progress_bar.progress(50)

                # 2. Quantum Run
                status_text.markdown(f"â³ Running Quantum (QAOA) Controller on {target_intersections}...")
                q_ctrl = QuantumOptimizerController(
                    p_layers=qaoa_p,
                    shots=qaoa_shots,
                    maxiter=qaoa_maxiter,
                    seed=42,
                )
                q_orch = SimulationOrchestrator(
                    controller=q_ctrl,
                    controller_name="Quantum-Live",
                    total_steps=run_steps,
                    optimization_interval=run_interval,
                    intersection_ids=target_intersections,
                    emergency_inject_step=run_steps // 2 if enable_emergency else None,
                    congestion_inject_step=int(run_steps * 0.6) if enable_congestion else None,
                    congestion_clear_step=int(run_steps * 0.85) if enable_congestion else None,
                )
                q_res = q_orch.run()

                progress_bar.progress(100)
                status_text.success("âœ… Simulation comparison complete!")

                res_col1, res_col2 = st.columns(2)
                with res_col1:
                    st.markdown("#### Classical Results")
                    st.json(c_res.final_metrics)
                with res_col2:
                    st.markdown("#### Quantum Results")
                    st.json(q_res.final_metrics)

            except Exception as e:
                st.error(f"Error executing live simulation: {e}")


# =============================================================================
# TAB 3: QAOA & QUBO DEEP DIVE
# =============================================================================
with tab_qaoa:
    st.markdown("### Quantum Approximate Optimization Algorithm (QAOA) Engine")

    qaoa_intro_col1, qaoa_intro_col2 = st.columns([3, 2])
    with qaoa_intro_col1:
        st.markdown(
            r"""
            #### Problem Formulation (QUBO)
            The urban traffic signal optimization is cast as a Quadratic Unconstrained Binary Optimization problem:
            
            $$\min_{x} \quad H(x) = x^T Q x = \sum_i Q_{ii} x_i + \sum_{i < j} Q_{ij} x_i x_j$$
            
            Where:
            * Binary variable $x(i, \text{phase}, \text{duration}) \in \{0, 1\}$ indicates choosing a specific configuration at intersection $i$.
            * **Penalty Term**: Enforces $\sum_{p, d} x(i, p, d) = 1$ with weight $\lambda_{\text{penalty}} = 1000$.
            * **Cost Model**: Computes remaining queues, approach wait times, throughput benefit, and emergency clearing.
            """
        )
    with qaoa_intro_col2:
        st.markdown(
            r"""
            #### Ising Mapping & QAOA Ansatz
            Using the Pauli-Z transformation $x_i = \frac{1 - Z_i}{2}$, the QUBO is mapped to an Ising Hamiltonian:
            
            $$H_C = \sum_i h_i Z_i + \sum_{i < j} J_{ij} Z_i Z_j + \text{offset}$$
            
            The QAOA state is evolved via $p$ alternating layers:
            
            $$|\gamma, \beta\rangle = \prod_{k=1}^p e^{-i \beta_k H_M} e^{-i \gamma_k H_C} |+\rangle^{\otimes N}$$
            """
        )

    st.markdown("---")

    saved_data = load_saved_results("demo_results.json")
    if saved_data and "qaoa_details" in saved_data["quantum"] and saved_data["quantum"]["qaoa_details"]:
        qd = saved_data["quantum"]["qaoa_details"]
        st.markdown("#### Latest QAOA Optimization Metrics")

        qd_col1, qd_col2, qd_col3, qd_col4 = st.columns(4)
        with qd_col1:
            st.metric("QUBO Objective Value", f"{qd.get('qubo_cost', 0.0):.4f}",
                      help="Total QUBO cost at selected bitstring. Lower = better traffic outcome.")
        with qd_col2:
            feasible = qd.get("is_feasible", False)
            st.metric("One-Hot Constraint", "âœ… Feasible" if feasible else "âš ï¸ Relaxed",
                      delta="Constraint satisfied" if feasible else "Fallback applied",
                      delta_color="normal" if feasible else "inverse")
        with qd_col3:
            st.metric("QAOA Eval Time", f"{qd.get('execution_time_seconds', 0.0):.4f} s",
                      help="Wall-clock time for QAOA optimization on Qiskit Aer simulator.")
        with qd_col4:
            st.metric("Ansatz Layers (p)", qd.get("p_layers", 1),
                      help="Higher p = more expressiveness, but exponentially more classical optimization.")

        st.markdown("---")
        st.markdown("#### Variational Parameters")
        param_col1, param_col2, param_col3 = st.columns(3)
        with param_col1:
            gamma_vals = qd.get("optimal_gamma", [])
            st.write("**Optimal Î³ (Phase Separation):**")
            for k, g in enumerate(gamma_vals):
                st.code(f"  gamma[{k}] = {g:.6f} rad", language="text")
        with param_col2:
            beta_vals = qd.get("optimal_beta", [])
            st.write("**Optimal Î² (Mixer Rotation):**")
            for k, b in enumerate(beta_vals):
                st.code(f"  beta[{k}]  = {b:.6f} rad", language="text")
        with param_col3:
            bitstring = qd.get("selected_bitstring", "")
            st.write("**Selected Bitstring:**")
            st.code(bitstring, language="text")
            n_vars = len(bitstring)
            n_active = bitstring.count("1")
            n_intersections = n_vars // 6
            st.caption(f"{n_vars} variables | {n_intersections} intersections | {n_active} active configs")

        st.markdown("---")
        st.markdown("#### Multi-Objective Cost Model Weights")
        st.markdown(
            """
            The QUBO objective combines seven components into a single scalar H(x):
            """
        )
        cost_data = {
            "Component": [
                "Queue (unserved green)",
                "Wait (red delay)",
                "Congestion (red density)",
                "Throughput Reward",
                "Stability Penalty",
                "Downstream Penalty",
                "Emergency Override",
                "Constraint Penalty (lambda)",
            ],
            "Weight": ["10.0", "8.0", "5.0", "-12.0 (reward)", "1.5", "8.0", "500.0", "1000.0"],
            "Range":  ["[0, 1]", "[0, 2]", "[0, 1]", "[-1, 0]", "{0, 1.5}", "[0, inf)", "large +/-", "0 or lambda"],
            "Role": [
                "Penalize residual unserved queue after green phase",
                "Penalize cumulative delay on red approaches",
                "Penalize high-density red-approach saturation",
                "Reward discharge of vehicles (negative cost)",
                "Discourage phase oscillation between cycles",
                "Penalize pushing traffic into saturated downstream",
                "Strictly prioritize emergency vehicle clearance",
                "Enforce exactly-one config per intersection",
            ],
        }
        st.dataframe(pd.DataFrame(cost_data), width='stretch', hide_index=True)

        is_fallback = qd.get("is_fallback", False)
        if is_fallback:
            st.warning(
                "**Classical Fallback Applied:** QAOA did not find a feasible one-hot bitstring. "
                "The most energy-minimizing feasible bitstring was selected via post-processing."
            )
    else:
        st.info(
            "No live QAOA telemetry found. Run `python run_hackathon_demo.py` first to generate "
            "`demo_results.json`, then reload this page."
        )


# =============================================================================
# TAB 4: NETWORK TOPOLOGY
# =============================================================================
with tab_network:
    st.markdown("### Urban Road Network Architecture")

    st.write(
        """
        The simulation environment models a coordinated urban corridor with 8 signalized intersections 
        arranged in a 2Ã—4 grid network, connected by bidirectional arterial roadways.
        """
    )

    # Intersection representation
    nodes = [
        {"id": "I1", "x": 0, "y": 1, "phase": "NS_GREEN", "lanes": "N, S, E, W"},
        {"id": "I2", "x": 1, "y": 1, "phase": "EW_GREEN", "lanes": "N, S, E, W"},
        {"id": "I3", "x": 2, "y": 1, "phase": "NS_GREEN", "lanes": "N, S, E, W"},
        {"id": "I4", "x": 3, "y": 1, "phase": "EW_GREEN", "lanes": "N, S, E, W"},
        {"id": "I5", "x": 0, "y": 0, "phase": "EW_GREEN", "lanes": "N, S, E, W"},
        {"id": "I6", "x": 1, "y": 0, "phase": "NS_GREEN", "lanes": "N, S, E, W"},
        {"id": "I7", "x": 2, "y": 0, "phase": "EW_GREEN", "lanes": "N, S, E, W"},
        {"id": "I8", "x": 3, "y": 0, "phase": "NS_GREEN", "lanes": "N, S, E, W"},
    ]
    df_nodes = pd.DataFrame(nodes)

    fig_grid = px.scatter(
        df_nodes,
        x="x",
        y="y",
        text="id",
        color="phase",
        color_discrete_map={"NS_GREEN": "#38bdf8", "EW_GREEN": "#34d399"},
        size_max=30,
    )
    fig_grid.update_traces(marker=dict(size=38, line=dict(width=2, color="#ffffff")), textposition="middle center", textfont=dict(size=14, color="white", family="JetBrains Mono"))
    fig_grid.update_layout(
        title="<b>Grid Network Layout (2Ã—4 Signalized Intersections)</b>",
        template="plotly_dark",
        paper_bgcolor="rgba(15,23,42,0.6)",
        plot_bgcolor="rgba(15,23,42,0.3)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=400,
        margin=dict(l=40, r=40, t=50, b=40),
    )
    st.plotly_chart(fig_grid, width='stretch')

    st.markdown("#### Approach Directions & Signal Assignment")
    st.dataframe(
        pd.DataFrame([
            {"Intersection": "I1", "North": "Queue: 2 | Cap: 50", "South": "Queue: 1 | Cap: 50", "East": "Queue: 4 | Cap: 50", "West": "Queue: 0 | Cap: 50", "Active Phase": "NS Green (30s)"},
            {"Intersection": "I2", "North": "Queue: 0 | Cap: 50", "South": "Queue: 3 | Cap: 50", "East": "Queue: 1 | Cap: 50", "West": "Queue: 2 | Cap: 50", "Active Phase": "EW Green (60s)"},
            {"Intersection": "I3", "North": "Queue: 5 | Cap: 50", "South": "Queue: 4 | Cap: 50", "East": "Queue: 0 | Cap: 50", "West": "Queue: 1 | Cap: 50", "Active Phase": "NS Green (60s)"},
            {"Intersection": "I4", "North": "Queue: 1 | Cap: 50", "South": "Queue: 0 | Cap: 50", "East": "Queue: 3 | Cap: 50", "West": "Queue: 0 | Cap: 50", "Active Phase": "EW Green (30s)"},
        ]),
        width='stretch',
    )


# =============================================================================
# TAB 5: BENCHMARK RESULTS
# =============================================================================
with tab_benchmark:
    st.markdown("### Multi-Scenario Benchmark Results")
    st.markdown(
        """
        Load results from `run_benchmark.py` â€” a reproducible runner that compares
        **Fixed-Cycle (A)**, **Classical Rule-Based (B)**, and **Quantum-QAOA (C)**
        across identical simulation conditions per scenario and seed.
        """
    )

    bench_data = load_benchmark_results("benchmark_results.json")

    if bench_data is None:
        st.info(
            "No `benchmark_results.json` found. Generate it with:\n\n"
            "```bash\n"
            "python run_benchmark.py --scenarios Normal,Emergency --seeds 1,2,3 --steps 200\n"
            "```"
        )
    else:
        st.success(
            f"Loaded benchmark from `benchmark_results.json`  "
            f"(generated: {bench_data.get('metadata', {}).get('timestamp', 'unknown')})"
        )
        records = bench_data.get("records", [])
        if records:
            df_all = pd.DataFrame(records)

            # Aggregate: mean over seeds per (scenario, controller)
            df_agg = (
                df_all[df_all["avg_waiting_time"] >= 0]
                .groupby(["scenario", "controller"], as_index=False)
                .agg(
                    avg_waiting_time=("avg_waiting_time", "mean"),
                    avg_queue_length=("avg_queue_length", "mean"),
                    final_throughput=("final_throughput", "mean"),
                    total_co2_kg=("total_co2_kg", "mean"),
                    wall_time_seconds=("wall_time_seconds", "mean"),
                )
            )

            # Color mapping
            CTRL_COLORS = {
                "A-Fixed":     "#94a3b8",
                "B-Classical": "#f59e0b",
                "C-Quantum":   "#38bdf8",
            }

            scenarios_present = df_agg["scenario"].unique().tolist()

            # --- Metric selector ---
            metric_choice = st.selectbox(
                "Metric to visualize",
                options=["avg_waiting_time", "avg_queue_length", "final_throughput", "total_co2_kg"],
                format_func=lambda m: {
                    "avg_waiting_time":  "Avg Waiting Time (s/veh)",
                    "avg_queue_length":  "Avg Queue Length (veh)",
                    "final_throughput":  "Total Completed Trips",
                    "total_co2_kg":      "Total CO2 Emissions (kg)",
                }[m],
            )

            lower_better = metric_choice in ("avg_waiting_time", "avg_queue_length", "total_co2_kg")

            # --- Grouped bar chart ---
            fig_bench = go.Figure()
            for ctrl_label in ["A-Fixed", "B-Classical", "C-Quantum"]:
                subset = df_agg[df_agg["controller"] == ctrl_label]
                fig_bench.add_trace(go.Bar(
                    name=ctrl_label,
                    x=subset["scenario"],
                    y=subset[metric_choice],
                    marker_color=CTRL_COLORS.get(ctrl_label, "#ffffff"),
                    opacity=0.88,
                ))

            y_label = {
                "avg_waiting_time": "Avg Wait (s)",
                "avg_queue_length": "Avg Queue (veh)",
                "final_throughput": "Completed Trips",
                "total_co2_kg":     "CO2 (kg)",
            }[metric_choice]

            fig_bench.update_layout(
                title=f"<b>{y_label} by Scenario and Controller</b>"
                      f"  <span style='font-size:13px; color:#94a3b8'>"
                      f"({'lower is better' if lower_better else 'higher is better'})</span>",
                barmode="group",
                template="plotly_dark",
                paper_bgcolor="rgba(15,23,42,0.6)",
                plot_bgcolor="rgba(15,23,42,0.3)",
                xaxis_title="Scenario",
                yaxis_title=y_label,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=40, r=20, t=60, b=40),
                height=420,
            )
            st.plotly_chart(fig_bench, width='stretch')

            # --- Summary table ---
            st.markdown("#### Detailed Averages (all seeds)")
            display_df = df_agg.rename(columns={
                "scenario":        "Scenario",
                "controller":      "Controller",
                "avg_waiting_time": "Avg Wait (s)",
                "avg_queue_length": "Avg Queue",
                "final_throughput": "Throughput",
                "total_co2_kg":     "CO2 (kg)",
                "wall_time_seconds": "Wall (s)",
            })
            st.dataframe(
                display_df[["Scenario", "Controller", "Avg Wait (s)", "Avg Queue",
                             "Throughput", "CO2 (kg)", "Wall (s)"]].round(3),
                width='stretch',
                hide_index=True,
            )

            st.caption(
                "\u26a0\ufe0f  Results show raw, unmodified simulation metrics. "
                "QAOA performance varies by scenario and seed. "
                "No metrics have been suppressed or rescaled."
            )
        else:
            st.warning("benchmark_results.json found but contains no records.")

