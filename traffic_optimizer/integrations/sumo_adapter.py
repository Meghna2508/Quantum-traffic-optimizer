"""SUMO Adapter mapping TraCI simulation to NetworkTrafficState and SignalDecisions."""

import os
from typing import Dict, List, Optional, Any, Tuple
import sumolib
import traci

from traffic_optimizer.config import SignalPhase, Direction, DEFAULT_ROAD_CAPACITY
from traffic_optimizer.controllers.signal_controller import SignalDecision
from traffic_optimizer.models.traffic_state import (
    IntersectionStateSnapshot,
    NetworkTrafficState,
)


class SUMOAdapter:
    """
    Adapter bridging SUMO TraCI simulation engine with our Quantum Traffic Optimizer architecture.

    SUMO -> QUANTUM: Converts TraCI vehicle queues & densities -> NetworkTrafficState.
    QUANTUM -> SUMO: Converts SignalDecision objects -> SUMO traffic light commands.
    """

    def __init__(
        self,
        config_path: str = "sumo/simulation.sumocfg",
        use_gui: bool = False,
        step_length: float = 1.0,
        intersections: Optional[List[str]] = None,
    ) -> None:
        self.config_path = config_path
        self.use_gui = use_gui
        self.step_length = step_length
        self.is_connected = False
        self._explicit_intersections = intersections
        self.intersections = (
            intersections
            if intersections is not None
            else ["I1", "I2", "I3", "I4"]
        )
        self.arrived_vehicles_count = 0
        self.emergency_vehicles_injected: Dict[str, float] = {}
        self.emergency_travel_times: Dict[str, float] = {}
        self.active_congestion_events: Dict[str, float] = {}  # edge_id -> original_max_speed
        self._saved_tls_programs: Dict[str, str] = {}
        self._preempted_tls: List[str] = []
        # Synthetic 2x2 IDs keep the original TraCI phase-index actuation path.
        self._synthetic_tls_ids = {"I1", "I2", "I3", "I4"}

    def start_simulation(self) -> None:
        """Launches SUMO or SUMO-GUI via TraCI."""
        if self.is_connected:
            return

        binary_name = "sumo-gui" if self.use_gui else "sumo"
        sumo_binary = sumolib.checkBinary(binary_name)

        sumo_cmd = [
            sumo_binary,
            "-c",
            self.config_path,
            "--step-length",
            str(self.step_length),
            "--no-warnings",
            "true",
        ]

        traci.start(sumo_cmd)
        self.is_connected = True
        if self._explicit_intersections is None:
            discovered = list(traci.trafficlight.getIDList())
            if discovered:
                self.intersections = discovered
        self._snapshot_tls_programs()

    def close(self) -> None:
        """Closes TraCI connection."""
        if self.is_connected:
            try:
                traci.close()
            except Exception:
                pass
            self.is_connected = False

    def step(self, seconds: int = 1) -> None:
        """Advances SUMO simulation by a given number of steps."""
        if not self.is_connected:
            self.start_simulation()

        for _ in range(seconds):
            traci.simulationStep()
            self.arrived_vehicles_count += traci.simulation.getArrivedNumber()

            # Track emergency vehicle travel times
            for veh_id in list(self.emergency_vehicles_injected.keys()):
                if veh_id in traci.vehicle.getIDList():
                    # Vehicle active
                    pass
                elif veh_id not in self.emergency_travel_times:
                    # Vehicle finished route
                    start_t = self.emergency_vehicles_injected[veh_id]
                    end_t = traci.simulation.getTime()
                    self.emergency_travel_times[veh_id] = round(end_t - start_t, 2)

    def extract_network_state(self) -> NetworkTrafficState:
        """
        Reads SUMO network state and builds an immutable NetworkTrafficState snapshot.

        Returns:
            NetworkTrafficState: Unified snapshot consumable by QUBO/QAOA.
        """
        if not self.is_connected:
            self.start_simulation()

        timestamp = traci.simulation.getTime()
        intersection_snapshots: Dict[str, IntersectionStateSnapshot] = {}

        for iid in self.intersections:
            snap = self._extract_intersection_snapshot(iid)
            intersection_snapshots[iid] = snap

        road_counts: Dict[str, int] = {}
        for edge_id in traci.edge.getIDList():
            if not edge_id.startswith(":"):
                road_counts[edge_id] = traci.edge.getLastStepVehicleNumber(edge_id)

        return NetworkTrafficState(
            timestamp=timestamp,
            intersections=intersection_snapshots,
            road_vehicle_counts=road_counts,
        )

    def _extract_intersection_snapshot(self, iid: str) -> IntersectionStateSnapshot:
        """Extracts queue, density, phase, and emergency status for single SUMO junction."""
        controlled_lanes = traci.trafficlight.getControlledLanes(iid)

        queue_lengths = {"N": 0, "S": 0, "E": 0, "W": 0}
        densities = {"N": 0.0, "S": 0.0, "E": 0.0, "W": 0.0}
        capacities = {"N": 50, "S": 50, "E": 50, "W": 50}
        emergency_status = {"N": False, "S": False, "E": False, "W": False}
        waiting_times = {"N": 0.0, "S": 0.0, "E": 0.0, "W": 0.0}
        approach_speeds = {"N": 13.89, "S": 13.89, "E": 13.89, "W": 13.89}
        speed_counts = {"N": 0, "S": 0, "E": 0, "W": 0}

        for lane in set(controlled_lanes):
            # Classify lane into cardinal direction (N, S, E, W) based on lane orientation
            direction = self._classify_lane_direction(lane, iid)

            veh_ids = traci.lane.getLastStepVehicleIDs(lane)
            halting = traci.lane.getLastStepHaltingNumber(lane)
            queue_lengths[direction] += halting

            lane_len = traci.lane.getLength(lane)
            lane_cap = max(1, int(lane_len / 7.5))
            capacities[direction] += lane_cap

            # Extract actual SUMO waiting time and speed
            try:
                lane_wait = traci.lane.getWaitingTime(lane)
                waiting_times[direction] += round(lane_wait, 2)
                lane_spd = traci.lane.getLastStepMeanSpeed(lane)
                if lane_spd >= 0:
                    current_avg = approach_speeds[direction]
                    cnt = speed_counts[direction]
                    approach_speeds[direction] = round((current_avg * cnt + lane_spd) / (cnt + 1), 2)
                    speed_counts[direction] += 1
            except Exception:
                pass

            # Check for emergency vehicles
            for v in veh_ids:
                if "emergency" in v.lower() or traci.vehicle.getTypeID(v) == "emergency":
                    emergency_status[direction] = True

        for d in ("N", "S", "E", "W"):
            cap = capacities[d]
            q = queue_lengths[d]
            densities[d] = round(min(1.0, q / float(cap)), 4)

        # Get current signal phase state from TraCI
        current_state_str = traci.trafficlight.getRedYellowGreenState(iid)
        current_phase = self._parse_sumo_phase_state(current_state_str)

        return IntersectionStateSnapshot(
            intersection_id=iid,
            queue_lengths=queue_lengths,
            densities=densities,
            capacities=capacities,
            current_phase=current_phase.value,
            current_green_duration=30,  # Default fallback duration
            emergency_status=emergency_status,
            waiting_times=waiting_times,
            approach_speeds=approach_speeds,
        )

    def apply_signal_decisions(self, decisions: Dict[str, SignalDecision]) -> None:
        """
        Translates SignalDecision objects into SUMO traffic light state settings.

        Args:
            decisions: Mapping from intersection_id -> SignalDecision.
        """
        if not self.is_connected:
            return

        for iid, decision in decisions.items():
            if iid in self.intersections:
                self._apply_intersection_decision(iid, decision)

    def _apply_intersection_decision(self, iid: str, decision: SignalDecision) -> None:
        """Sets phase state for a single junction in SUMO."""
        # Preserve the validated 2x2 actuation path (phase index 0 = NS, 2 = EW).
        if iid in self._synthetic_tls_ids:
            phase_idx = 0 if decision.phase == SignalPhase.NORTH_SOUTH else 2
            try:
                traci.trafficlight.setPhase(iid, phase_idx)
                traci.trafficlight.setPhaseDuration(iid, float(decision.duration))
                return
            except traci.TraCIException:
                try:
                    curr_state = traci.trafficlight.getRedYellowGreenState(iid)
                    half = max(1, len(curr_state) // 2)
                    if decision.phase == SignalPhase.NORTH_SOUTH:
                        state_str = "G" * half + "r" * (len(curr_state) - half)
                    else:
                        state_str = "r" * half + "G" * (len(curr_state) - half)
                    traci.trafficlight.setRedYellowGreenState(iid, state_str)
                    return
                except Exception:
                    return
        self._apply_geometric_phase(iid, decision)

    def _apply_geometric_phase(self, iid: str, decision: SignalDecision) -> None:
        """Map NS/EW decisions onto OSM (or other) TLS using approach geometry."""
        try:
            lanes = traci.trafficlight.getControlledLanes(iid)
            if not lanes:
                return
            want_ns = decision.phase == SignalPhase.NORTH_SOUTH
            chars: List[str] = []
            for lane in lanes:
                direction = self._classify_lane_direction(lane, iid)
                is_ns = direction in ("N", "S")
                chars.append("G" if is_ns == want_ns else "r")
            traci.trafficlight.setRedYellowGreenState(iid, "".join(chars))
            try:
                traci.trafficlight.setPhaseDuration(iid, float(decision.duration))
            except traci.TraCIException:
                pass
        except Exception:
            pass

    def _snapshot_tls_programs(self) -> None:
        """Record the loaded SUMO programs so emergency preemption can restore them."""
        self._saved_tls_programs = {}
        try:
            for tls_id in traci.trafficlight.getIDList():
                self._saved_tls_programs[tls_id] = traci.trafficlight.getProgram(tls_id)
        except Exception:
            self._saved_tls_programs = {}

    def restore_tls_programs(self) -> List[str]:
        """Restore the original signal programs after corridor preemption."""
        restored: List[str] = []
        if not self.is_connected:
            return restored
        for tls_id, program in self._saved_tls_programs.items():
            try:
                traci.trafficlight.setProgram(tls_id, program)
                restored.append(tls_id)
            except Exception:
                continue
        self._preempted_tls = []
        return restored

    def tls_on_route(self, route_edges: List[str]) -> List[str]:
        """Return traffic-light IDs that control any edge on the given route."""
        if not self.is_connected:
            return []
        route_set = set(route_edges)
        matched: List[str] = []
        for tls_id in traci.trafficlight.getIDList():
            try:
                lanes = traci.trafficlight.getControlledLanes(tls_id)
            except traci.TraCIException:
                continue
            incoming = {lane.rsplit("_", 1)[0] for lane in lanes}
            if incoming & route_set:
                matched.append(tls_id)
        return matched

    def apply_emergency_corridor(self, vehicle_id: str) -> List[str]:
        """
        Preempt only signalized intersections on the emergency vehicle's remaining
        route. Unrelated traffic lights are left unchanged.
        """
        if not self.is_connected:
            return []
        try:
            if vehicle_id not in traci.vehicle.getIDList():
                return []
            route_edges = list(traci.vehicle.getRoute(vehicle_id))
            try:
                current_idx = traci.vehicle.getRouteIndex(vehicle_id)
                remaining = set(route_edges[max(0, current_idx) :])
            except traci.TraCIException:
                remaining = set(route_edges)
        except traci.TraCIException:
            return []

        preempted: List[str] = []
        for tls_id in traci.trafficlight.getIDList():
            try:
                lanes = list(traci.trafficlight.getControlledLanes(tls_id))
            except traci.TraCIException:
                continue
            route_link_indices = [
                i for i, lane in enumerate(lanes) if lane.rsplit("_", 1)[0] in remaining
            ]
            if not route_link_indices:
                continue
            state = ["r"] * len(lanes)
            for i in route_link_indices:
                state[i] = "G"
            try:
                traci.trafficlight.setRedYellowGreenState(tls_id, "".join(state))
                preempted.append(tls_id)
            except traci.TraCIException:
                continue
        self._preempted_tls = preempted
        return preempted

    def inject_emergency_vehicle(
        self, route_id: str = "R1", vehicle_id: str = "emergency_1"
    ) -> str:
        """Injects an emergency vehicle onto a specified SUMO route."""
        if not self.is_connected:
            self.start_simulation()

        try:
            # Ensure emergency vehicle type exists with prominent emergency styling
            if "emergency" not in traci.vehicletype.getIDList():
                try:
                    traci.vehicletype.copy("car", "emergency")
                except Exception:
                    pass
                try:
                    traci.vehicletype.setColor("emergency", (255, 0, 0, 255))
                    traci.vehicletype.setSpeedFactor("emergency", 1.8)
                    traci.vehicletype.setVehicleClass("emergency", "emergency")
                    traci.vehicletype.setShapeClass("emergency", "emergency")
                except Exception:
                    pass

            traci.vehicle.add(
                vehID=vehicle_id,
                routeID=route_id,
                typeID="emergency",
                depart="now",
            )
            traci.vehicle.setColor(vehicle_id, (255, 0, 0, 255))
            self.emergency_vehicles_injected[vehicle_id] = traci.simulation.getTime()
            return vehicle_id
        except traci.TraCIException as e:
            return f"Error injecting: {e}"

    def get_metrics(self) -> Dict[str, Any]:
        """
        Collects real simulation metrics from SUMO/TraCI.

        Returns:
            Dict containing vehicle count, waiting times, queue counts, throughput, fuel & CO2.
        """
        if not self.is_connected:
            return {
                "vehicle_count": 0,
                "total_waiting_time": 0.0,
                "avg_waiting_time": 0.0,
                "total_queue": 0,
                "throughput": 0,
                "fuel_consumption_liters": 0.0,
                "co2_emissions_kg": 0.0,
                "emergency_travel_times": {},
            }

        active_vehicles = traci.vehicle.getIDList()
        num_vehicles = len(active_vehicles)

        total_waiting_time = sum(
            traci.vehicle.getWaitingTime(v) for v in active_vehicles
        )

        avg_waiting_time = (
            round(total_waiting_time / float(num_vehicles), 2) if num_vehicles > 0 else 0.0
        )

        # Estimate fuel (mg/s) and CO2 (mg/s) from active vehicles
        total_fuel_mg = sum(
            traci.vehicle.getFuelConsumption(v) for v in active_vehicles
        )
        total_co2_mg = sum(
            traci.vehicle.getCO2Emission(v) for v in active_vehicles
        )

        # Convert mg -> liters (approx 750,000 mg/L) and mg -> kg (1,000,000 mg/kg)
        fuel_liters = round(total_fuel_mg / 750000.0, 3)
        co2_kg = round(total_co2_mg / 1000000.0, 3)

        total_queue = 0
        for iid in self.intersections:
            lanes = traci.trafficlight.getControlledLanes(iid)
            for lane in set(lanes):
                vehs = traci.lane.getLastStepVehicleIDs(lane)
                total_queue += sum(1 for v in vehs if traci.vehicle.getSpeed(v) < 0.5)

        return {
            "vehicle_count": num_vehicles,
            "total_waiting_time": round(total_waiting_time, 2),
            "avg_waiting_time": avg_waiting_time,
            "total_queue": total_queue,
            "throughput": self.arrived_vehicles_count,
            "fuel_consumption_liters": fuel_liters,
            "co2_emissions_kg": co2_kg,
            "emergency_travel_times": dict(self.emergency_travel_times),
        }
    def inject_congestion_event(
        self,
        edge_id: str,
        speed_reduction_factor: float = 0.2,
    ) -> str:
        """
        Simulates a traffic incident by reducing max speed on an edge.

        Args:
            edge_id: SUMO edge ID (e.g., 'I1_I2').
            speed_reduction_factor: Fraction of original speed to keep (0.2 = 80% reduction).

        Returns:
            Status message string.
        """
        if not self.is_connected:
            self.start_simulation()

        try:
            if edge_id in self.active_congestion_events:
                return f"Congestion already active on {edge_id}"

            lane_0 = f"{edge_id}_0"
            try:
                original_speed = traci.lane.getMaxSpeed(lane_0)
            except Exception:
                original_speed = 13.89  # standard SUMO 50 km/h default
            self.active_congestion_events[edge_id] = original_speed
            reduced_speed = max(0.5, original_speed * speed_reduction_factor)
            traci.edge.setMaxSpeed(edge_id, reduced_speed)
            return f"Congestion injected on {edge_id}: {original_speed:.1f} -> {reduced_speed:.1f} m/s"
        except traci.TraCIException as e:
            return f"Error injecting congestion on {edge_id}: {e}"

    def clear_congestion_event(self, edge_id: str) -> str:
        """
        Restores original speed on an edge after a congestion event.

        Args:
            edge_id: SUMO edge ID to restore.

        Returns:
            Status message string.
        """
        if not self.is_connected:
            return f"Not connected, cannot clear {edge_id}"

        if edge_id not in self.active_congestion_events:
            return f"No active congestion on {edge_id}"

        try:
            original_speed = self.active_congestion_events.pop(edge_id)
            traci.edge.setMaxSpeed(edge_id, original_speed)
            return f"Congestion cleared on {edge_id}: speed restored to {original_speed:.1f} m/s"
        except traci.TraCIException as e:
            return f"Error clearing congestion on {edge_id}: {e}"

    def clear_all_congestion_events(self) -> None:
        """Clears all active congestion events."""
        for edge_id in list(self.active_congestion_events.keys()):
            self.clear_congestion_event(edge_id)

    def _classify_lane_direction(self, lane_id: str, iid: str) -> str:
        """Determines cardinal approach direction ('N','S','E','W') for a lane leading to iid."""
        edge_id = lane_id.rsplit("_", 1)[0]
        mapping = {
            "I1": {"N1_I1": "N", "I3_I1": "S", "I2_I1": "E", "W1_I1": "W"},
            "I2": {"N2_I2": "N", "I4_I2": "S", "E2_I2": "E", "I1_I2": "W"},
            "I3": {"I1_I3": "N", "S3_I3": "S", "I4_I3": "E", "W3_I3": "W"},
            "I4": {"I2_I4": "N", "S4_I4": "S", "E4_I4": "E", "I3_I4": "W"},
        }
        if iid in mapping and edge_id in mapping[iid]:
            return mapping[iid][edge_id]

        geometric = self._geometric_lane_direction(lane_id)
        if geometric is not None:
            return geometric

        if "N" in edge_id:
            return "N"
        elif "S" in edge_id:
            return "S"
        elif "E" in edge_id:
            return "E"
        elif "W" in edge_id:
            return "W"
        return "N"

    @staticmethod
    def _geometric_lane_direction(lane_id: str) -> Optional[str]:
        """Classify an approaching lane from its shape: travel heading implies origin."""
        try:
            shape = traci.lane.getShape(lane_id)
        except Exception:
            return None
        if not shape or len(shape) < 2:
            return None
        x0, y0 = shape[-2]
        x1, y1 = shape[-1]
        dx = x1 - x0
        dy = y1 - y0
        if dx == 0 and dy == 0:
            return None
        if abs(dy) >= abs(dx):
            return "S" if dy > 0 else "N"
        return "W" if dx > 0 else "E"

    @staticmethod
    def _parse_sumo_phase_state(state_str: str) -> SignalPhase:
        """Parses SUMO traffic light state string to SignalPhase."""
        half = max(1, len(state_str) // 2)
        ns_greens = sum(1 for c in state_str[:half] if c in ("G", "g"))
        ew_greens = sum(1 for c in state_str[half:] if c in ("G", "g"))
        if ns_greens >= ew_greens:
            return SignalPhase.NORTH_SOUTH
        return SignalPhase.EAST_WEST
