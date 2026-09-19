"""Simulation orchestrator bridging SUMO adapter with Classical/Quantum controllers."""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from traffic_optimizer.controllers.signal_controller import BaseSignalController, SignalDecision
from traffic_optimizer.integrations.sumo_adapter import SUMOAdapter


@dataclass
class StepMetrics:
    """Metrics captured at a single simulation step."""
    step: int
    sim_time: float
    vehicle_count: int
    total_waiting_time: float
    avg_waiting_time: float
    total_queue: int
    throughput: int
    fuel_consumption_liters: float
    co2_emissions_kg: float
    decisions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    events: List[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Complete simulation run results."""
    controller_name: str
    total_steps: int
    optimization_interval: int
    wall_time_seconds: float
    step_metrics: List[StepMetrics] = field(default_factory=list)
    emergency_travel_times: Dict[str, float] = field(default_factory=dict)
    qaoa_details: Optional[Dict[str, Any]] = None

    @property
    def final_metrics(self) -> Dict[str, Any]:
        """Returns summary metrics from the final step."""
        if not self.step_metrics:
            return {}
        last = self.step_metrics[-1]
        avg_wait_all = 0.0
        avg_queue_all = 0.0
        if self.step_metrics:
            avg_wait_all = sum(m.avg_waiting_time for m in self.step_metrics) / len(self.step_metrics)
            avg_queue_all = sum(m.total_queue for m in self.step_metrics) / len(self.step_metrics)
        return {
            "controller": self.controller_name,
            "total_steps": self.total_steps,
            "wall_time_seconds": round(self.wall_time_seconds, 2),
            "final_vehicle_count": last.vehicle_count,
            "final_throughput": last.throughput,
            "avg_waiting_time": round(avg_wait_all, 2),
            "avg_queue_length": round(avg_queue_all, 2),
            "total_fuel_liters": round(sum(m.fuel_consumption_liters for m in self.step_metrics), 3),
            "total_co2_kg": round(sum(m.co2_emissions_kg for m in self.step_metrics), 3),
            "emergency_travel_times": self.emergency_travel_times,
        }


class SimulationOrchestrator:
    """
    Runs a complete SUMO simulation loop with a given signal controller.

    Supports:
    - Periodic optimization (extract state -> controller decisions -> apply to SUMO)
    - Emergency vehicle injection at configurable step
    - Congestion event injection/clearing at configurable steps
    - Per-step metric collection for dashboard visualization
    """

    def __init__(
        self,
        controller: BaseSignalController,
        controller_name: str = "controller",
        config_path: str = "sumo/simulation.sumocfg",
        total_steps: int = 500,
        optimization_interval: int = 30,
        use_gui: bool = False,
        intersection_ids: Optional[List[str]] = None,
        emergency_inject_step: Optional[int] = None,
        emergency_route: str = "R1",
        congestion_inject_step: Optional[int] = None,
        congestion_clear_step: Optional[int] = None,
        congestion_edge: str = "I1_I2",
        congestion_reduction: float = 0.2,
        emergency_preemption: bool = False,
    ) -> None:
        self.controller = controller
        self.controller_name = controller_name
        self.config_path = config_path
        self.total_steps = total_steps
        self.optimization_interval = optimization_interval
        self.use_gui = use_gui
        self.intersection_ids = intersection_ids
        self.emergency_inject_step = emergency_inject_step
        self.emergency_route = emergency_route
        self.congestion_inject_step = congestion_inject_step
        self.congestion_clear_step = congestion_clear_step
        self.congestion_edge = congestion_edge
        self.congestion_reduction = congestion_reduction
        self.emergency_preemption = emergency_preemption

    def run(self, progress_callback=None) -> SimulationResult:
        """
        Executes the full simulation loop.

        Args:
            progress_callback: Optional callable(step, total_steps) for progress updates.

        Returns:
            SimulationResult with full metric timeseries.
        """
        adapter = SUMOAdapter(
            config_path=self.config_path,
            use_gui=self.use_gui,
            intersections=self.intersection_ids,
        )

        step_metrics_list: List[StepMetrics] = []
        qaoa_details = None
        start_wall = time.time()

        try:
            adapter.start_simulation()

            for step in range(1, self.total_steps + 1):
                events: List[str] = []

                # --- Dynamic Events ---
                trigger_optimization = (step % self.optimization_interval == 0)

                if self.emergency_inject_step and step == self.emergency_inject_step:
                    veh_id = f"emergency_{self.controller_name}"
                    result = adapter.inject_emergency_vehicle(
                        route_id=self.emergency_route,
                        vehicle_id=veh_id,
                    )
                    events.append(f"Emergency injected: {result}")
                    trigger_optimization = True

                if self.congestion_inject_step and step == self.congestion_inject_step:
                    result = adapter.inject_congestion_event(
                        edge_id=self.congestion_edge,
                        speed_reduction_factor=self.congestion_reduction,
                    )
                    events.append(f"Congestion: {result}")
                    trigger_optimization = True

                if self.congestion_clear_step and step == self.congestion_clear_step:
                    result = adapter.clear_congestion_event(self.congestion_edge)
                    events.append(f"Congestion cleared: {result}")
                    trigger_optimization = True

                # --- Advance SUMO Simulation ---
                adapter.step(seconds=1)

                emergency_veh_id = f"emergency_{self.controller_name}"
                corridor_active = False
                if self.emergency_preemption and emergency_veh_id in adapter.emergency_vehicles_injected:
                    if emergency_veh_id not in adapter.emergency_travel_times:
                        preempted = adapter.apply_emergency_corridor(emergency_veh_id)
                        if preempted:
                            corridor_active = True
                            msg = f"Emergency corridor preempted TLS: {preempted}"
                            already_logged = any(
                                "Emergency corridor preempted TLS:" in e
                                for m in step_metrics_list
                                for e in m.events
                            )
                            if not already_logged:
                                events.append(msg)
                    elif adapter._preempted_tls:
                        restored = adapter.restore_tls_programs()
                        if restored:
                            events.append(f"Normal signal programs restored: {restored}")
                            trigger_optimization = True

                # Check if emergency vehicle completed its route
                if self.emergency_inject_step and step > self.emergency_inject_step:
                    veh_id = f"emergency_{self.controller_name}"
                    if veh_id in adapter.emergency_travel_times:
                        cleared_msg = f"Emergency corridor cleared: {veh_id}"
                        if cleared_msg not in [e for m in step_metrics_list for e in m.events]:
                            events.append(cleared_msg)
                            trigger_optimization = True

                # --- Adaptive / Periodic / Event-driven Optimization ---
                decisions_dict: Dict[str, Dict[str, Any]] = {}
                if trigger_optimization:
                    network_state = adapter.extract_network_state()
                    decisions = self.controller.get_decisions(network_state)
                    if not corridor_active:
                        adapter.apply_signal_decisions(decisions)
                    else:
                        # Keep corridor greens; still record optimizer intent.
                        pass

                    decisions_dict = {
                        iid: d.to_dict() for iid, d in decisions.items()
                    }

                    # Capture QAOA details if available
                    if hasattr(self.controller, "last_result") and self.controller.last_result is not None:
                        result = self.controller.last_result
                        qaoa_details = {
                            "selected_bitstring": result.selected_bitstring,
                            "qubo_cost": result.qubo_cost,
                            "is_feasible": result.is_feasible,
                            "p_layers": result.p_layers,
                            "optimal_gamma": list(result.optimal_gamma),
                            "optimal_beta": list(result.optimal_beta),
                            "execution_time_seconds": result.execution_time_seconds,
                            "is_fallback": result.is_fallback,
                        }

                # --- Collect Metrics ---
                metrics = adapter.get_metrics()
                step_m = StepMetrics(
                    step=step,
                    sim_time=float(step),
                    vehicle_count=metrics["vehicle_count"],
                    total_waiting_time=metrics["total_waiting_time"],
                    avg_waiting_time=metrics["avg_waiting_time"],
                    total_queue=metrics["total_queue"],
                    throughput=metrics["throughput"],
                    fuel_consumption_liters=metrics["fuel_consumption_liters"],
                    co2_emissions_kg=metrics["co2_emissions_kg"],
                    decisions=decisions_dict,
                    events=events,
                )
                step_metrics_list.append(step_m)

                if progress_callback:
                    progress_callback(step, self.total_steps)

        finally:
            adapter.clear_all_congestion_events()
            emergency_travel_times = dict(adapter.emergency_travel_times)
            adapter.close()

        wall_time = time.time() - start_wall

        return SimulationResult(
            controller_name=self.controller_name,
            total_steps=self.total_steps,
            optimization_interval=self.optimization_interval,
            wall_time_seconds=wall_time,
            step_metrics=step_metrics_list,
            emergency_travel_times=emergency_travel_times,
            qaoa_details=qaoa_details,
        )
