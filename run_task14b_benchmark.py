#!/usr/bin/env python3
"""
TASK 14B - Scientific Benchmark on optimize branch
Branch: optimize  Commit: 4e19435

Network: 2x2 grid, 4 TL intersections (I1, I2, I3, I4)
Valid edges: I1_I2, I2_I1, I1_I3, I3_I1, I2_I4, I4_I2, I3_I4, I4_I3
              N1_I1, N2_I2, W1_I1, W3_I3, E2_I2, E4_I4, S3_I3, S4_I4

Differences from quantum-optimization branch:
- w_congestion: 5.0 -> 8.0
- w_downstream: 8.0 -> 12.0
- w_emissions: new term = 5.0
- cost_model: emissions proxy added (red idling + residual queue)
- Congestion edge FIXED: was 'I2_I3' (invalid), now 'I1_I2' (valid)
"""

import json, os, sys, time, statistics, csv, traceback
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any

from traffic_optimizer.config import QUBOConfig, SignalPhase, ALLOWED_GREEN_DURATIONS
from traffic_optimizer.controllers.signal_controller import (
    BaseSignalController, ClassicalRuleBasedController, SignalDecision,
)
from traffic_optimizer.controllers.quantum_controller import QuantumOptimizerController
from traffic_optimizer.models.traffic_state import NetworkTrafficState
from traffic_optimizer.integrations.orchestrator import SimulationOrchestrator
from traffic_optimizer.optimization.qubo import TrafficQUBOBuilder, TrafficQUBODecoder


class FixedCycleController(BaseSignalController):
    def __init__(self):
        self._call_count = 0
    def get_decisions(self, state):
        phase = SignalPhase.NORTH_SOUTH if self._call_count % 2 == 0 else SignalPhase.EAST_WEST
        self._call_count += 1
        return {iid: SignalDecision(phase=phase, duration=30) for iid in state.intersections}


class InstrumentedQAOA(QuantumOptimizerController):
    """Wraps QAOA controller to capture per-call chunk diagnostics."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.call_log = []
        self._qb = TrafficQUBOBuilder(config=kwargs.get("qubo_config", QUBOConfig()))

    def get_decisions(self, state):
        iids = sorted(state.intersections.keys())
        if not iids: return {}
        chunk_size = 3
        groups = [iids[i:i+chunk_size] for i in range(0, len(iids), chunk_size)]
        entry = {"num_intersections": len(iids), "num_groups": len(groups),
                 "groups": [list(g) for g in groups],
                 "qubits_per_group": [], "group_results": []}
        all_dec = {}
        for gi, group in enumerate(groups):
            t0 = time.time()
            qubo = self._qb.build_qubo(state, target_intersection_ids=group)
            res = self.solver.solve(qubo)
            self.last_result = res
            elapsed = time.time() - t0
            gd = TrafficQUBODecoder.decode(res.selected_bitstring, qubo)
            all_dec.update(gd)
            entry["qubits_per_group"].append(qubo.num_variables)
            entry["group_results"].append({
                "group_idx": gi, "intersections": group,
                "num_qubits": qubo.num_variables,
                "selected_bitstring": res.selected_bitstring,
                "qubo_cost": round(res.qubo_cost, 6),
                "is_feasible": res.is_feasible,
                "is_fallback": res.is_fallback,
                "exec_time_s": round(elapsed, 4),
                "decisions_given": sorted(gd.keys()),
                "missing": [i for i in group if i not in gd],
            })
        entry["max_qubits"] = max(entry["qubits_per_group"]) if entry["qubits_per_group"] else 0
        entry["any_fallback"] = any(g["is_fallback"] for g in entry["group_results"])
        entry["any_infeasible"] = any(not g["is_feasible"] for g in entry["group_results"])
        self.call_log.append(entry)
        return all_dec


@dataclass
class ScenarioCfg:
    name: str
    emergency_step: Optional[int]
    congestion_inject_step: Optional[int]
    congestion_clear_step: Optional[int]
    congestion_edge: str   # MUST be a valid edge in this network


SCENARIOS = {
    "Normal":     ScenarioCfg("Normal",     None, None, None, "I1_I2"),
    "Congestion": ScenarioCfg("Congestion", None, 20,   180,  "I1_I2"),   # FIXED: was I2_I3
    "Emergency":  ScenarioCfg("Emergency",  35,   None, None, "I1_I2"),
}

SEEDS    = [42, 43, 44, 45, 46]
STEPS    = 200
INTERVAL = 30
SHOTS    = 512
MAXITER  = 15

BRANCH = "optimize"
COMMIT = "4e19435"


@dataclass
class RunRecord:
    scenario: str
    controller: str
    seed: int
    avg_waiting_time: float
    avg_queue_length: float
    max_queue_length: float
    final_throughput: int
    active_vehicles_final: int
    total_fuel_liters: float
    total_co2_kg: float
    wall_time_seconds: float
    emergency_travel_time: Optional[float]
    emergency_corridor_completed: bool
    qaoa_num_calls: int = 0
    qaoa_num_groups: int = 0
    qaoa_max_qubits: int = 0
    qaoa_fallback_count: int = 0
    qaoa_infeasible_count: int = 0
    qaoa_avg_exec_time_s: float = 0.0
    qaoa_call_log_sample: Optional[List] = field(default=None)
    error: Optional[str] = None


def run_one(ctrl_label, ctrl, scen, seed):
    orch = SimulationOrchestrator(
        controller=ctrl, controller_name=ctrl_label,
        total_steps=STEPS, optimization_interval=INTERVAL, use_gui=False,
        intersection_ids=None,
        emergency_inject_step=scen.emergency_step,
        congestion_inject_step=scen.congestion_inject_step,
        congestion_clear_step=scen.congestion_clear_step,
        congestion_edge=scen.congestion_edge,
    )
    result = orch.run()
    fm = result.final_metrics
    max_q = max((m.total_queue for m in result.step_metrics), default=0)
    emerg_tt = None; emerg_ok = False
    if result.emergency_travel_times:
        emerg_tt = next(iter(result.emergency_travel_times.values()), None)
        emerg_ok = emerg_tt is not None

    qaoa_calls=qaoa_groups=qaoa_maxq=qaoa_fb=qaoa_inf=0
    qaoa_exec=0.0; sample=None
    if isinstance(ctrl, InstrumentedQAOA) and ctrl.call_log:
        qaoa_calls = len(ctrl.call_log)
        first = ctrl.call_log[0]
        qaoa_groups = first["num_groups"]
        qaoa_maxq = max(c["max_qubits"] for c in ctrl.call_log)
        qaoa_fb = sum(1 for c in ctrl.call_log if c["any_fallback"])
        qaoa_inf = sum(1 for c in ctrl.call_log if c["any_infeasible"])
        all_exec = [g["exec_time_s"] for c in ctrl.call_log for g in c["group_results"]]
        qaoa_exec = statistics.mean(all_exec) if all_exec else 0.0
        sample = ctrl.call_log[:1]

    return RunRecord(
        scenario=scen.name, controller=ctrl_label, seed=seed,
        avg_waiting_time=fm.get("avg_waiting_time", 0.0),
        avg_queue_length=fm.get("avg_queue_length", 0.0),
        max_queue_length=float(max_q),
        final_throughput=fm.get("final_throughput", 0),
        active_vehicles_final=fm.get("final_vehicle_count", 0),
        total_fuel_liters=fm.get("total_fuel_liters", 0.0),
        total_co2_kg=fm.get("total_co2_kg", 0.0),
        wall_time_seconds=round(fm.get("wall_time_seconds", 0.0), 3),
        emergency_travel_time=emerg_tt,
        emergency_corridor_completed=emerg_ok,
        qaoa_num_calls=qaoa_calls, qaoa_num_groups=qaoa_groups,
        qaoa_max_qubits=qaoa_maxq, qaoa_fallback_count=qaoa_fb,
        qaoa_infeasible_count=qaoa_inf,
        qaoa_avg_exec_time_s=round(qaoa_exec, 5),
        qaoa_call_log_sample=sample,
    )


def analyse_components(state, iid, phase, dur):
    from traffic_optimizer.optimization.cost_model import TrafficCostModel
    cm = TrafficCostModel()
    cfg = cm.config
    snap = state.get_intersection(iid)
    gd = ("N","S") if phase=="NS" else ("E","W")
    rd = ("E","W") if phase=="NS" else ("N","S")
    gq = sum(snap.queue_lengths.get(d,0) for d in gd)
    rq = sum(snap.queue_lengths.get(d,0) for d in rd)
    gc = sum(snap.capacities.get(d,50) for d in gd)
    rc = sum(snap.capacities.get(d,50) for d in rd)
    disch = min(float(gq), float(dur))
    rem   = max(0.0, float(gq) - disch)
    c_q   = cfg.w_queue * (rem / max(1.0, float(gc)))
    aw    = sum(getattr(snap,"waiting_times",{}).get(d,0.0) for d in rd)
    nw    = min(2.0, (aw + rq*dur) / max(1.0, float(rc)*120.0))
    c_w   = cfg.w_wait * nw
    rd_   = sum(snap.densities.get(d,0.0) for d in rd) / max(1.0, float(len(rd)))
    c_co  = cfg.w_congestion * min(1.0, rd_*(dur/90.0))
    # emissions proxy (optimize branch adds this)
    nr_i  = min(1.0, rq/max(1.0,float(rc)))
    nr_r  = min(1.0, rem/max(1.0,float(gc)))
    c_em  = cfg.w_emissions * min(1.0, 0.65*nr_i + 0.35*nr_r + 0.25*rd_) if hasattr(cfg,'w_emissions') else 0.0
    r_t   = -cfg.w_throughput * min(1.0, disch/max(1.0,90.0))
    c_sw  = cfg.w_switch if (snap.current_phase and phase!=snap.current_phase) else 0.0
    c_ds  = cm._compute_downstream_penalty(iid, phase, dur, state)
    c_emg = 0.0
    df = dur/30.0
    for d in gd:
        if snap.emergency_status.get(d,False): c_emg -= cfg.w_emergency*df
    for d in rd:
        if snap.emergency_status.get(d,False): c_emg += 2.0*cfg.w_emergency*df
    total = c_q+c_w+c_co+c_em+r_t+c_sw+c_ds+c_emg
    return {"iid":iid,"phase":phase,"dur":dur,
            "cost_queue":round(c_q,4),"cost_wait":round(c_w,4),
            "cost_congestion":round(c_co,4),"cost_emissions":round(c_em,4),
            "reward_throughput":round(r_t,4),"cost_switch":round(c_sw,4),
            "cost_downstream":round(c_ds,4),"cost_emergency":round(c_emg,4),
            "total":round(total,4)}


def st(vals):
    if not vals: return {"mean":None,"median":None,"std":None,"min":None,"max":None}
    return {"mean":round(statistics.mean(vals),3),
            "median":round(statistics.median(vals),3),
            "std":round(statistics.stdev(vals),3) if len(vals)>1 else 0.0,
            "min":round(min(vals),3),"max":round(max(vals),3)}


def main():
    print("\n"+"="*80)
    print("  TASK 14B - OPTIMIZE BRANCH SCIENTIFIC BENCHMARK")
    print(f"  Branch: {BRANCH} | Commit: {COMMIT}")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print(f"  Network: 2x2 grid | TL nodes: I1,I2,I3,I4")
    print(f"  Scenarios: {list(SCENARIOS.keys())} | Seeds: {SEEDS}")
    print(f"  Steps:{STEPS} Interval:{INTERVAL} Shots:{SHOTS} Maxiter:{MAXITER}")
    print(f"  Congestion edge corrected to 'I1_I2' (I2_I3 invalid in this network)")
    print("="*80)

    records = []
    total = len(SCENARIOS)*len(SEEDS)*3; idx=0

    for sname, scen in SCENARIOS.items():
        for seed in SEEDS:
            ctrls = [
                ("A-Fixed",     lambda s=seed: FixedCycleController()),
                ("B-Classical", lambda s=seed: ClassicalRuleBasedController()),
                ("C-Quantum",   lambda s=seed: InstrumentedQAOA(
                    qubo_config=QUBOConfig(), p_layers=1, shots=SHOTS, maxiter=MAXITER, seed=s)),
            ]
            for clabel, make_c in ctrls:
                idx+=1; ctrl=make_c()
                print(f"\n  [{idx:>3}/{total}] {sname:<12} Seed={seed} {clabel}", flush=True)
                t0=time.time()
                try:
                    rec = run_one(clabel, ctrl, scen, seed)
                    records.append(rec)
                    print(f"    wait={rec.avg_waiting_time:.3f}s queue={rec.avg_queue_length:.3f} "
                          f"maxQ={rec.max_queue_length:.0f} thru={rec.final_throughput} "
                          f"fuel={rec.total_fuel_liters:.3f}L CO2={rec.total_co2_kg:.3f}kg "
                          f"wall={rec.wall_time_seconds:.2f}s", flush=True)
                    if clabel=="C-Quantum":
                        print(f"    QAOA calls={rec.qaoa_num_calls} groups={rec.qaoa_num_groups} "
                              f"maxQubits={rec.qaoa_max_qubits} fallbacks={rec.qaoa_fallback_count} "
                              f"infeasible={rec.qaoa_infeasible_count} "
                              f"avgExec={rec.qaoa_avg_exec_time_s:.4f}s", flush=True)
                        if rec.qaoa_call_log_sample:
                            s0 = rec.qaoa_call_log_sample[0]
                            print(f"    Chunking: intersections={s0['num_intersections']} "
                                  f"groups={s0['num_groups']} "
                                  f"qubits_per_group={s0['qubits_per_group']}", flush=True)
                            for gr in s0["group_results"]:
                                print(f"      grp{gr['group_idx']}:{gr['intersections']} "
                                      f"{gr['num_qubits']}qb feasible={gr['is_feasible']} "
                                      f"fallback={gr['is_fallback']} cost={gr['qubo_cost']:.6f} "
                                      f"decisions={gr['decisions_given']} missing={gr['missing']}", flush=True)
                    if scen.emergency_step:
                        print(f"    Emergency: tt={rec.emergency_travel_time} "
                              f"completed={rec.emergency_corridor_completed}", flush=True)
                except Exception as exc:
                    elapsed = round(time.time()-t0, 2)
                    print(f"    ERROR [{elapsed:.1f}s]: {exc}")
                    traceback.print_exc()
                    records.append(RunRecord(
                        scenario=sname, controller=clabel, seed=seed,
                        avg_waiting_time=-1, avg_queue_length=-1, max_queue_length=-1,
                        final_throughput=-1, active_vehicles_final=-1,
                        total_fuel_liters=-1, total_co2_kg=-1, wall_time_seconds=elapsed,
                        emergency_travel_time=None, emergency_corridor_completed=False,
                        error=str(exc)))

    # Section 6: QUBO objective component analysis
    print("\n"+"="*80)
    print("  SECTION 8: OBJECTIVE COMPONENT ANALYSIS (optimize branch)")
    print("="*80)
    try:
        from traffic_optimizer.integrations.sumo_adapter import SUMOAdapter
        adp = SUMOAdapter(config_path="sumo/simulation.sumocfg", use_gui=False)
        adp.start_simulation()
        adp.step(seconds=5)
        ns = adp.extract_network_state()
        adp.close()
        cfg = QUBOConfig()
        print(f"  optimize QUBOConfig: w_congestion={cfg.w_congestion} "
              f"w_downstream={cfg.w_downstream} w_emissions={cfg.w_emissions}")
        iids = sorted(ns.intersections.keys())
        print(f"  Inspecting intersections: {iids[:2]}")
        for iid in iids[:2]:
            print(f"\n  {iid}:")
            for phase in ["NS","EW"]:
                for dur in [30,60,90]:
                    c = analyse_components(ns, iid, phase, dur)
                    print(f"    ({phase},{dur}s): queue={c['cost_queue']:+.4f} "
                          f"wait={c['cost_wait']:+.4f} cong={c['cost_congestion']:+.4f} "
                          f"emis={c['cost_emissions']:+.4f} thru={c['reward_throughput']:+.4f} "
                          f"switch={c['cost_switch']:+.4f} ds={c['cost_downstream']:+.4f} "
                          f"emg={c['cost_emergency']:+.4f} TOTAL={c['total']:+.4f}")
    except Exception as e:
        print(f"  Component analysis error: {e}")
        traceback.print_exc()

    # Section 5: Chunking verification summary
    print("\n"+"="*80)
    print("  SECTION 6: CHUNKING VERIFICATION (runtime evidence)")
    print("="*80)
    qn42 = [r for r in records if r.scenario=="Normal" and r.controller=="C-Quantum"
             and r.seed==42 and not r.error]
    if qn42 and qn42[0].qaoa_call_log_sample:
        s0 = qn42[0].qaoa_call_log_sample[0]
        print(f"  Verified from Normal/Seed=42 first QAOA call:")
        print(f"  num_intersections : {s0['num_intersections']}")
        print(f"  num_groups        : {s0['num_groups']}")
        print(f"  qubits_per_group  : {s0['qubits_per_group']}")
        print(f"  max_qubits        : {s0['max_qubits']}")
        print(f"  48-qubit circuit  : {'YES - OOM risk' if s0['max_qubits']>=48 else 'NO - within limits'}")
        print(f"  OOM observed      : No (run completed)")
        for gr in s0["group_results"]:
            print(f"    group {gr['group_idx']}: {gr['intersections']} -> "
                  f"{gr['num_qubits']} qubits | missing={gr['missing']}")
    else:
        print("  No Normal/seed42 QAOA run available for chunking verification.")

    # Section 11: Multi-seed statistics
    print("\n"+"="*80)
    print("  SECTION 11: MULTI-SEED STATISTICS")
    print("="*80)
    stat_summary = {}
    for sname in SCENARIOS:
        stat_summary[sname] = {}
        for ctrl in ["A-Fixed","B-Classical","C-Quantum"]:
            good = [r for r in records if r.scenario==sname and r.controller==ctrl and not r.error]
            errs = [r for r in records if r.scenario==sname and r.controller==ctrl and r.error]
            stat_summary[sname][ctrl] = {
                "n_ok": len(good), "n_err": len(errs),
                "avg_waiting_time": st([r.avg_waiting_time for r in good]),
                "avg_queue_length": st([r.avg_queue_length for r in good]),
                "throughput":       st([r.final_throughput for r in good]),
                "fuel":             st([r.total_fuel_liters for r in good]),
                "co2":              st([r.total_co2_kg for r in good]),
                "wall_time":        st([r.wall_time_seconds for r in good]),
                "emergency_tt":     st([r.emergency_travel_time for r in good if r.emergency_travel_time is not None]),
                "qaoa_max_qubits":  st([r.qaoa_max_qubits for r in good]) if ctrl=="C-Quantum" else None,
                "qaoa_fallback_rate": (round(sum(r.qaoa_fallback_count for r in good)/max(1,sum(r.qaoa_num_calls for r in good)),4) if ctrl=="C-Quantum" and good else None),
            }
            ss = stat_summary[sname][ctrl]
            print(f"\n  Scenario={sname} | Controller={ctrl} | n={ss['n_ok']} runs (errors={ss['n_err']})")
            print(f"    AvgWait (s):  {ss['avg_waiting_time']}")
            print(f"    AvgQueue:     {ss['avg_queue_length']}")
            print(f"    Throughput:   {ss['throughput']}")
            print(f"    Fuel (L):     {ss['fuel']}")
            print(f"    CO2  (kg):    {ss['co2']}")
            if sname=="Emergency": print(f"    EmergTT (s):  {ss['emergency_tt']}")
            if ctrl=="C-Quantum":
                print(f"    MaxQubits:    {ss['qaoa_max_qubits']}")
                print(f"    FallbackRate: {ss['qaoa_fallback_rate']}")

    # Per-seed raw table
    print("\n"+"="*80)
    print("  PER-SEED RAW RESULTS")
    print("="*80)
    for sname in SCENARIOS:
        print(f"\n  Scenario: {sname}")
        print(f"  {'Ctrl':<14}{'Seed':>5}{'Wait':>9}{'Queue':>8}{'MaxQ':>7}{'Thru':>7}{'Fuel':>9}{'CO2':>9}{'Wall':>8}{'EmgTT':>8}")
        for ctrl in ["A-Fixed","B-Classical","C-Quantum"]:
            for r in [r for r in records if r.scenario==sname and r.controller==ctrl]:
                if r.error:
                    print(f"  {ctrl:<14}{r.seed:>5}  ERROR: {r.error[:60]}")
                else:
                    et = f"{r.emergency_travel_time:.1f}" if r.emergency_travel_time else "N/A"
                    print(f"  {ctrl:<14}{r.seed:>5}{r.avg_waiting_time:>9.3f}{r.avg_queue_length:>8.3f}"
                          f"{r.max_queue_length:>7.0f}{r.final_throughput:>7}"
                          f"{r.total_fuel_liters:>9.3f}{r.total_co2_kg:>9.3f}"
                          f"{r.wall_time_seconds:>8.2f}{et:>8}")

    # Save JSON
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = {
        "metadata": {
            "task": "Task14B", "branch": BRANCH, "commit": COMMIT,
            "timestamp": ts, "scenarios": list(SCENARIOS.keys()),
            "seeds": SEEDS, "steps": STEPS, "interval": INTERVAL,
            "shots": SHOTS, "maxiter": MAXITER,
            "network": "sumo/simulation.sumocfg",
            "intersections": ["I1","I2","I3","I4"],
            "congestion_edge": "I1_I2",
            "note_congestion_fix": "Previous benchmark used invalid edge I2_I3; corrected to I1_I2",
            "optimize_changes_vs_quantum_optimization": {
                "w_congestion": "5.0 -> 8.0",
                "w_downstream": "8.0 -> 12.0",
                "w_emissions": "new, =5.0",
                "cost_model": "emissions proxy term added",
            },
            "qubo_config": {k:v for k,v in vars(QUBOConfig()).items()},
        },
        "statistical_summary": stat_summary,
        "records": [asdict(r) for r in records],
    }
    with open("benchmark_results.json","w") as f: json.dump(out,f,indent=2,default=str)
    print("\n[+] Saved benchmark_results.json")

    with open("benchmark_results.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["branch","commit","scenario","controller","seed",
                    "avg_waiting_time","avg_queue_length","max_queue_length",
                    "final_throughput","total_fuel_liters","total_co2_kg",
                    "wall_time_seconds","emergency_travel_time","emergency_corridor_completed",
                    "qaoa_num_calls","qaoa_num_groups","qaoa_max_qubits",
                    "qaoa_fallback_count","qaoa_infeasible_count","qaoa_avg_exec_time_s","error"])
        for r in records:
            w.writerow([BRANCH,COMMIT,r.scenario,r.controller,r.seed,
                        r.avg_waiting_time,r.avg_queue_length,r.max_queue_length,
                        r.final_throughput,r.total_fuel_liters,r.total_co2_kg,
                        r.wall_time_seconds,r.emergency_travel_time,
                        r.emergency_corridor_completed,r.qaoa_num_calls,
                        r.qaoa_num_groups,r.qaoa_max_qubits,r.qaoa_fallback_count,
                        r.qaoa_infeasible_count,r.qaoa_avg_exec_time_s,r.error or ""])
    print("[+] Saved benchmark_results.csv")
    print("\n[DONE]")
    return records

if __name__=="__main__":
    main()
