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
        self.intersections = (
            intersections
            if intersections is not None
            else ["I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8"]
        )
        self.arrived_vehicles_count = 0
        self.emergency_vehicles_injected: Dict[str, float] = {}
        self.emergency_travel_times: Dict[str, float] = {}
        self.active_congestion_events: Dict[str, float] = {}  # edge_id -> original_max_speed

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
        # SUMO standard 2-lane traffic light state pattern:
        # Phase 0: North/South Green ("GgGgrrrrGgGgrrrr" or "GGggrrrrGGggrrrr")
        # Phase 2: East/West Green   ("rrrrGGggrrrrGGgg")
        if decision.phase == SignalPhase.NORTH_SOUTH:
            state_str = "GgGgrrrrGgGgrrrr"
        else:
            state_str = "rrrrGgGgrrrrGgGg"

        try:
            # Set state string dynamically
            traci.trafficlight.setRedYellowGreenState(iid, state_str)
        except traci.TraCIException:
            pass

    def inject_emergency_vehicle(
        self, route_id: str = "R1", vehicle_id: str = "emergency_1"
    ) -> str:
        """Injects an emergency vehicle onto a specified SUMO route."""
        if not self.is_connected:
            self.start_simulation()

        try:
            # Ensure emergency vehicle type exists
            if "emergency" not in traci.vehicletype.getIDList():
                traci.vehicletype.copy("car", "emergency")
                traci.vehicletype.setColor("emergency", (255, 0, 0, 255))
                traci.vehicletype.setSpeedFactor("emergency", 1.5)

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

    @staticmethod
    def _classify_lane_direction(lane_id: str, iid: str) -> str:
        """Determines cardinal approach direction ('N','S','E','W') for a lane leading to iid."""
        if "I1_" in lane_id or "I5_" in lane_id:
            return "W"
        elif "I4_" in lane_id or "I8_" in lane_id:
            return "E"
        elif "_I1" in lane_id or "_I2" in lane_id or "_I3" in lane_id or "_I4" in lane_id:
            return "N"
        else:
            return "S"

    @staticmethod
    def _parse_sumo_phase_state(state_str: str) -> SignalPhase:
        """Parses SUMO traffic light state string to SignalPhase."""
        # If first 4 chars have 'G' or 'g', North-South is green
        if len(state_str) >= 4 and ("G" in state_str[:4] or "g" in state_str[:4]):
            return SignalPhase.NORTH_SOUTH
        return SignalPhase.EAST_WEST
