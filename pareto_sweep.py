"""
pareto_sweep.py — Price of Priority analysis
=============================================

Sweeps ambulance-priority QUBO weight λ over a fixed scenario and measures:

    X  =  ambulance travel time saved  (seconds)
    Y  =  additional network delay      (seconds)

relative to the λ=0 (no-priority) baseline.

Produces:
    pareto.pkl       — pickled sweep data (loadable by Streamlit)
    pareto_chart.png — publication-quality Pareto trade-off plot

Usage:
    python pareto_sweep.py

Dependencies: matplotlib, numpy (optional), standard library only.
"""

from __future__ import annotations

import copy
import math
import pickle
import os
import sys
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ============================================================
# REAL PROJECT INTEGRATION
# Replace these imports with the actual project modules.
#
# Preferred:
#   from traffic_optimizer.quantum.qaoa_solver import solve
#   from traffic_optimizer.simulation.traffic_simulator import simulate_forward
#
# Both callables must satisfy:
#   action = solve(state, lam)
#   result = simulate_forward(state, action_sequence, n_ticks)
#   result keys required: "total_wait_s", "amb_travel_s", "amb_cleared"
#
# Set USE_REAL_PROJECT = True once those imports work.
# ============================================================

USE_REAL_PROJECT: bool = False

if USE_REAL_PROJECT:
    # from traffic_optimizer.quantum.qaoa_solver import solve
    # from traffic_optimizer.simulation.traffic_simulator import simulate_forward
    pass


# ============================================================
# MOCK IMPLEMENTATIONS  (deterministic — NOT real QUBO solutions)
# ============================================================

def mock_solve(state: Dict[str, Any], lam: float) -> Dict[str, Any]:
    """Deterministic mock solver. Higher λ biases signals toward ambulance route."""
    signals: Dict[str, int] = {}
    amb = state.get("ambulance", {})
    route_set = set(amb.get("route", []) if amb.get("active", False) else [])
    for node, sig in state.get("signals", {}).items():
        if node in route_set and lam > 0:
            bias = min(1.0, lam / 50.0)
            signals[node] = 1 if bias >= 0.5 else sig
        else:
            signals[node] = sig
    return {"signals": signals, "lam": lam}


def mock_simulate_forward(
    state: Dict[str, Any],
    action_sequence: List[Dict[str, Any]],
    n_ticks: int,
) -> Dict[str, Any]:
    """
    Deterministic mock simulator.

    Trade-off model (demo, not empirical — fixed seed, no randomness):
        amb_travel_s  = 40 * exp(-0.028 * lam)         diminishing returns
        total_wait_s  = 120 + 0.60 * lam / (1+lam/70)  saturating growth
    """
    if not action_sequence:
        raise ValueError("action_sequence must contain at least one action.")
    lam = float(action_sequence[0].get("lam", 0.0))
    amb_travel_s = 40.0 * math.exp(-0.028 * lam)
    total_wait_s = 120.0 + 0.60 * lam / (1.0 + lam / 70.0)
    return {
        "total_wait_s": total_wait_s,
        "amb_travel_s": amb_travel_s,
        "amb_cleared":  amb_travel_s < 28.0,
    }


# ── Bind to real or mock ────────────────────────────────────────────────────

if USE_REAL_PROJECT:
    raise RuntimeError("Set USE_REAL_PROJECT=False or complete real imports above.")
else:
    _solve = mock_solve
    _simulate_forward = mock_simulate_forward


# ============================================================
# FROZEN SCENARIO
# ============================================================

def make_frozen_scenario() -> Dict[str, Any]:
    """
    Returns a single deterministic scenario with an active ambulance.
    Replace this body with your real project fixture if available.
    """
    return {
        "t": 0,
        "queues":   {"I1>I2": 8, "I2>I3": 5, "I3>I4": 3, "I4>I5": 2, "I5>I6": 6},
        "capacity": {"I1>I2": 20,"I2>I3": 20,"I3>I4": 20,"I4>I5": 20,"I5>I6": 20},
        "signals":  {"I0":0,"I1":1,"I2":0,"I3":1,"I4":0,"I5":0,"I6":1},
        "ambulance": {
            "active": True,
            "route": ["I3","I4","I5"],
            "position": "I3",
            "eta": {"I4":3,"I5":7},
            "phase_needed": {"I4":0,"I5":0},
            "elapsed_s": 0.0,
            "cleared": False,
        },
        "event": None,
    }


def _assert_ambulance_active(state: Dict[str, Any]) -> None:
    if not state.get("ambulance", {}).get("active", False):
        raise ValueError("Frozen scenario must have ambulance['active'] == True.")


# ============================================================
# DATA TYPE
# ============================================================

class SweepPoint:
    """One evaluated (λ, result) record."""
    __slots__ = ("lam","amb_saved_s","network_cost_s","ratio",
                 "amb_travel_s","total_wait_s","amb_cleared","dominated")

    def __init__(self, lam, amb_saved_s, network_cost_s,
                 amb_travel_s, total_wait_s, amb_cleared):
        self.lam            = lam
        self.amb_saved_s    = amb_saved_s
        self.network_cost_s = network_cost_s
        self.amb_travel_s   = amb_travel_s
        self.total_wait_s   = total_wait_s
        self.amb_cleared    = amb_cleared
        self.dominated      = False
        self.ratio: Optional[float] = (
            network_cost_s / amb_saved_s if amb_saved_s > 1e-9 else None
        )

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}


# ============================================================
# LAMBDA SWEEP
# ============================================================

LAMBDAS: List[float] = [0, 5, 10, 20, 30, 45, 60, 80, 100]
N_TICKS: int = 15


def _validate_result(result: Dict[str, Any], lam: float) -> None:
    required = ("total_wait_s", "amb_travel_s", "amb_cleared")
    missing = [k for k in required if k not in result]
    if missing:
        raise ValueError(f"simulate_forward() for λ={lam} missing keys: {missing}")


def run_sweep(
    frozen_state: Dict[str, Any],
    lambdas: List[float] = LAMBDAS,
    n_ticks: int = N_TICKS,
) -> List[SweepPoint]:
    """
    Evaluates every λ against the identical frozen scenario.
    The frozen state is deep-copied before every call — no mutation.
    action_sequence = [action] * n_ticks for each λ.
    """
    _assert_ambulance_active(frozen_state)

    # baseline at λ=0
    r0 = _simulate_forward(
        copy.deepcopy(frozen_state),
        [_solve(copy.deepcopy(frozen_state), 0.0)] * n_ticks,
        n_ticks,
    )
    _validate_result(r0, 0.0)
    base_amb  = r0["amb_travel_s"]
    base_wait = r0["total_wait_s"]
    print(f"  Baseline (λ=0): amb={base_amb:.3f}s  wait={base_wait:.3f}s")

    points: List[SweepPoint] = []
    for lam in sorted(lambdas):
        action = _solve(copy.deepcopy(frozen_state), lam)
        result = _simulate_forward(copy.deepcopy(frozen_state), [action]*n_ticks, n_ticks)
        _validate_result(result, lam)
        pt = SweepPoint(
            lam            = lam,
            amb_saved_s    = base_amb  - result["amb_travel_s"],
            network_cost_s = result["total_wait_s"] - base_wait,
            amb_travel_s   = result["amb_travel_s"],
            total_wait_s   = result["total_wait_s"],
            amb_cleared    = result["amb_cleared"],
        )
        points.append(pt)
        r = f"{pt.ratio:.4f}" if pt.ratio is not None else "None"
        print(f"  λ={lam:>5.0f}: saved={pt.amb_saved_s:+.4f}s  "
              f"cost={pt.network_cost_s:+.4f}s  ratio={r}")
    return points


# ============================================================
# PARETO FILTER
# ============================================================

def compute_pareto(points: List[SweepPoint]) -> List[SweepPoint]:
    """
    Marks dominated points. Returns non-dominated subset sorted by amb_saved_s.
    maximize amb_saved_s, minimize network_cost_s.
    NOT claimed to be the continuous Pareto frontier.
    """
    for i, b in enumerate(points):
        for a in points:
            if a is b:
                continue
            if (a.amb_saved_s >= b.amb_saved_s and
                a.network_cost_s <= b.network_cost_s and
                (a.amb_saved_s > b.amb_saved_s or
                 a.network_cost_s < b.network_cost_s)):
                b.dominated = True
                break
    frontier = [p for p in points if not p.dominated]
    frontier.sort(key=lambda p: p.amb_saved_s)
    return frontier


# ============================================================
# KNEE DETECTION
# ============================================================

def find_knee(frontier: List[SweepPoint]) -> Optional[SweepPoint]:
    """
    Maximum perpendicular distance from chord (first→last frontier point).
    x = amb_saved_s, y = network_cost_s.
    Returns None when fewer than 3 frontier points.
    """
    if len(frontier) < 3:
        print("  [knee] <3 frontier points — knee=None")
        return None
    x0,y0 = frontier[0].amb_saved_s,  frontier[0].network_cost_s
    x1,y1 = frontier[-1].amb_saved_s, frontier[-1].network_cost_s
    dx, dy = x1-x0, y1-y0
    L = math.hypot(dx, dy)
    if L < 1e-12:
        return frontier[0]
    best_d, knee = -1.0, None
    for pt in frontier[1:-1]:
        d = abs(dy*pt.amb_saved_s - dx*pt.network_cost_s + x1*y0 - y1*x0) / L
        if d > best_d:
            best_d, knee = d, pt
    return knee


# ============================================================
# PICKLE I/O
# ============================================================

PICKLE_PATH = "pareto.pkl"

def save_pickle(points, frontier, knee, lambdas, horizon):
    payload = {
        "points":   [p.to_dict() for p in points],
        "frontier": [p.to_dict() for p in frontier],
        "knee":     knee.to_dict() if knee else None,
        "lambdas":  lambdas,
        "horizon":  horizon,
    }
    with open(PICKLE_PATH, "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  Saved: {PICKLE_PATH}")

def load_pickle(path=PICKLE_PATH):
    with open(path,"rb") as fh:
        return pickle.load(fh)


# ============================================================
# PLOTTING  (matplotlib only — no seaborn)
# ============================================================

CHART_PATH = "pareto_chart.png"

_COL_DOM   = "#9e9e9e"
_COL_FRONT = "#1565C0"
_COL_KNEE  = "#E53935"
_COL_SEL   = "#F9A825"


def pareto_chart(points, selected_lam=None):
    """
    Returns a matplotlib Figure of the Pareto trade-off.
    'Deployed systems' label is a presentation annotation only.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10,6.5), dpi=150)
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#F8F9FA")

    dom    = [p for p in points if     p.dominated]
    nondom = [p for p in points if not p.dominated]
    nondom.sort(key=lambda p: p.amb_saved_s)
    knee   = find_knee(nondom)

    # shade post-knee region
    if knee and len(nondom) >= 3:
        ki = nondom.index(knee)
        post = nondom[ki:]
        if len(post) >= 2:
            xs = [p.amb_saved_s    for p in post]
            ys = [p.network_cost_s for p in post]
            ax.fill_betweenx(ys, [0]*len(ys), xs,
                alpha=0.08, color=_COL_FRONT, zorder=1,
                label="Where deployed preemption\nsystems operate today")

    # dashed line through all λ points
    all_s = sorted(points, key=lambda p: p.lam)
    ax.plot([p.amb_saved_s for p in all_s],
            [p.network_cost_s for p in all_s],
            color="#BDBDBD", lw=1.2, ls="--", zorder=2)

    # dominated
    if dom:
        ax.scatter([p.amb_saved_s for p in dom],
                   [p.network_cost_s for p in dom],
                   color=_COL_DOM, s=55, zorder=4,
                   label="Dominated (λ sweep point)")

    # non-dominated frontier
    if nondom:
        ax.plot([p.amb_saved_s for p in nondom],
                [p.network_cost_s for p in nondom],
                color=_COL_FRONT, lw=2.2, zorder=5)
        ax.scatter([p.amb_saved_s for p in nondom],
                   [p.network_cost_s for p in nondom],
                   color=_COL_FRONT, s=70, marker="D", zorder=6,
                   label="Non-dominated (sampled Pareto frontier)")
        for p in nondom:
            ax.annotate(f"λ={p.lam:.0f}",
                xy=(p.amb_saved_s, p.network_cost_s),
                xytext=(4,6), textcoords="offset points",
                fontsize=7.5, color=_COL_FRONT, zorder=7)

    # knee
    if knee:
        ax.scatter([knee.amb_saved_s],[knee.network_cost_s],
                   color=_COL_KNEE, s=160, marker="*", zorder=8,
                   label=f"Knee  λ={knee.lam:.0f}")
        ax.annotate("Knee — best value\nper second bought",
            xy=(knee.amb_saved_s, knee.network_cost_s),
            xytext=(14,-22), textcoords="offset points",
            fontsize=9, color=_COL_KNEE, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=_COL_KNEE, lw=1.4), zorder=9)

    # selected λ
    if selected_lam is not None:
        matches = [p for p in points if abs(p.lam-selected_lam)<1e-6]
        if matches:
            sp = matches[0]
            ax.scatter([sp.amb_saved_s],[sp.network_cost_s],
                       color=_COL_SEL, s=130, marker="^",
                       edgecolors="k", lw=0.8, zorder=10,
                       label=f"Selected  λ={selected_lam:.0f}")

    ax.set_xlabel("Ambulance time saved  (s)", fontsize=12, labelpad=8)
    ax.set_ylabel("Network delay added  (s)",  fontsize=12, labelpad=8)
    ax.set_title(
        "Price of Priority — Ambulance Preemption Trade-off\n"
        "Quantum Green Corridor  |  Ambulance Priority λ sweep",
        fontsize=13, fontweight="bold", pad=14)
    ax.tick_params(labelsize=10)
    ax.grid(True, ls=":", lw=0.7, alpha=0.6, color="#BDBDBD")
    for sp_ in ax.spines.values():
        sp_.set_edgecolor("#CCCCCC")
    ax.legend(fontsize=9, loc="upper left", framealpha=0.92, edgecolor="#AAAAAA")
    ax.text(0.99,0.015,
        "Note: sampled Pareto frontier only. 'Deployed systems' label is a "
        "presentation annotation, not an empirical finding.",
        transform=ax.transAxes, fontsize=6.5, color="#888888",
        ha="right", va="bottom", style="italic")
    fig.tight_layout()
    return fig


# ============================================================
# PRINT TABLE
# ============================================================

def print_table(points):
    print()
    hdr = f"  {'λ':>6}  {'Amb saved':>10}  {'Net cost':>10}  {'Ratio':>9}  {'Cleared':>8}  {'Pareto':>7}"
    print(hdr)
    print("  " + "-"*65)
    for p in sorted(points, key=lambda x: x.lam):
        r = f"{p.ratio:.4f}" if p.ratio is not None else "     —"
        pr = "YES" if not p.dominated else "no"
        print(f"  {p.lam:>6.0f}  {p.amb_saved_s:>10.4f}  {p.network_cost_s:>10.4f}  "
              f"{r:>9}  {str(p.amb_cleared):>8}  {pr:>7}")
    print()


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("="*64)
    print("  Pareto Sweep — Price of Priority")
    print(f"  Mode   : {'REAL PROJECT' if USE_REAL_PROJECT else 'MOCK (demo data)'}")
    print(f"  λ grid : {LAMBDAS}")
    print(f"  Horizon: {N_TICKS} ticks")
    print("="*64)

    print("\n[1] Frozen scenario ...")
    frozen = make_frozen_scenario()
    _assert_ambulance_active(frozen)
    print(f"  ambulance.active   : {frozen['ambulance']['active']}")
    print(f"  ambulance.route    : {frozen['ambulance']['route']}")
    print(f"  ambulance.position : {frozen['ambulance']['position']}")

    print("\n[2] λ sweep ...")
    points = run_sweep(frozen, LAMBDAS, N_TICKS)

    print("\n[3] Pareto filter ...")
    frontier = compute_pareto(points)
    print(f"  Total: {len(points)}  |  Non-dominated: {len(frontier)}  |  Dominated: {len(points)-len(frontier)}")

    print("\n[4] Knee detection ...")
    knee = find_knee(frontier)
    if knee:
        print(f"  Knee at λ={knee.lam:.0f}  amb_saved={knee.amb_saved_s:.4f}s  net_cost={knee.network_cost_s:.4f}s")
    else:
        print("  Knee: None")

    print("[5] Sweep table:")
    print_table(points)

    print("[6] Saving pareto.pkl ...")
    save_pickle(points, frontier, knee, LAMBDAS, N_TICKS)

    print("[7] Generating pareto_chart.png ...")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = pareto_chart(points, selected_lam=knee.lam if knee else None)
    fig.savefig(CHART_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {CHART_PATH}")

    print("\n[8] Verifying outputs ...")
    loaded = load_pickle()
    assert "points"   in loaded
    assert "frontier" in loaded
    assert "knee"     in loaded
    assert os.path.getsize(CHART_PATH) > 1000
    print(f"  pareto.pkl       : {os.path.getsize(PICKLE_PATH):,} bytes  OK")
    print(f"  pareto_chart.png : {os.path.getsize(CHART_PATH):,} bytes  OK")
    print(f"\n  Knee λ = {knee.lam if knee else None}")
    print("\n[DONE]")
    print("="*64)

if __name__ == "__main__":
    main()
