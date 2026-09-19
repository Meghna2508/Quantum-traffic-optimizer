"""Cost model evaluating normalized multi-objective components (queue, delay, throughput, congestion, downstream, stability, emergency)."""

from typing import Dict, Tuple, List, Optional
from traffic_optimizer.config import QUBOConfig, DEFAULT_DISCHARGE_RATE
from traffic_optimizer.models.traffic_state import NetworkTrafficState, IntersectionStateSnapshot


# Topology connectivity for downstream bottlenecks (2x4 grid network)
DOWNSTREAM_TOPOLOGY: Dict[str, Dict[str, List[str]]] = {
    "I1": {"EW": ["I2"], "NS": ["I5"]},
    "I2": {"EW": ["I3", "I1"], "NS": ["I6"]},
    "I3": {"EW": ["I4", "I2"], "NS": ["I7"]},
    "I4": {"EW": ["I3"], "NS": ["I8"]},
    "I5": {"EW": ["I6"], "NS": ["I1"]},
    "I6": {"EW": ["I7", "I5"], "NS": ["I2"]},
    "I7": {"EW": ["I8", "I6"], "NS": ["I3"]},
    "I8": {"EW": ["I7"], "NS": ["I4"]},
}


class TrafficCostModel:
    """
    Evaluates traffic cost for candidate signal configurations at intersections.

    Principles of Multi-Objective Cost Model:
    1. Dimensionless Normalization:
       All primary metrics (queues, delay, congestion, throughput, downstream utilization)
       are scaled into canonical ranges [0, 1] or [0, 2] before linear combination.
    2. Throughput as Reward:
       Serving vehicles is modeled as a negative cost (reward) proportional to throughput.
    3. Signal Stability (Phase-Switching Penalty):
       Discourages high-frequency toggling between NS and EW across consecutive cycles.
    4. Network-Aware Downstream Penalty:
       Penalizes pushing traffic into saturated downstream corridors.
    5. Emergency Override:
       Provides strict dominance for clearing emergency vehicles.
    """

    def __init__(
        self,
        config: QUBOConfig = QUBOConfig(),
        discharge_rate: float = float(DEFAULT_DISCHARGE_RATE),
    ) -> None:
        self.config = config
        self.discharge_rate = discharge_rate

    def compute_candidate_cost(
        self,
        intersection_snap: IntersectionStateSnapshot,
        phase: str,
        duration: int,
        network_state: NetworkTrafficState,
    ) -> float:
        """
        Computes total linear cost H_{i, p, d} for candidate (phase, duration) at an intersection.

        Args:
            intersection_snap: Snapshot of the target intersection.
            phase: 'NS' or 'EW'.
            duration: Discrete green duration in seconds (30, 60, 90).
            network_state: Network-wide snapshot for downstream context.

        Returns:
            float: Cost value for this candidate configuration.
        """
        green_dirs = ("N", "S") if phase == "NS" else ("E", "W")
        red_dirs = ("E", "W") if phase == "NS" else ("N", "S")

        green_cap = sum(intersection_snap.capacities.get(d, 50) for d in green_dirs)
        red_cap = sum(intersection_snap.capacities.get(d, 50) for d in red_dirs)

        green_queue = sum(intersection_snap.queue_lengths.get(d, 0) for d in green_dirs)
        red_queue = sum(intersection_snap.queue_lengths.get(d, 0) for d in red_dirs)

        # 1. Unserved Remaining Queue (Normalized by green capacity)
        potential_discharge = self.discharge_rate * duration
        discharged = min(float(green_queue), potential_discharge)
        remaining_green_queue = max(0.0, float(green_queue) - discharged)
        normalized_queue = remaining_green_queue / max(1.0, float(green_cap))
        cost_queue = self.config.w_queue * normalized_queue

        # 2. Waiting Delay Cost on Red Approaches (Normalized)
        actual_wait = sum(getattr(intersection_snap, "waiting_times", {}).get(d, 0.0) for d in red_dirs)
        expected_wait_surge = red_queue * duration
        total_delay = actual_wait + expected_wait_surge
        normalized_wait = min(2.0, total_delay / max(1.0, float(red_cap) * 120.0))
        cost_wait = self.config.w_wait * normalized_wait

        # 3. Congestion Ratio Cost (Red direction occupancy)
        red_density = sum(intersection_snap.densities.get(d, 0.0) for d in red_dirs) / max(1.0, float(len(red_dirs)))
        normalized_congestion = min(1.0, red_density * (duration / 90.0))
        cost_congestion = self.config.w_congestion * normalized_congestion

        # 4. Throughput Reward (Negative cost, normalized by max possible 90s discharge)
        max_possible_discharge = self.discharge_rate * 90.0
        normalized_throughput = min(1.0, discharged / max(1.0, max_possible_discharge))
        reward_throughput = -self.config.w_throughput * normalized_throughput

        # 5. Signal Stability / Phase-Switching Penalty
        cost_switch = 0.0
        if intersection_snap.current_phase and phase != intersection_snap.current_phase:
            cost_switch = self.config.w_switch

        # 6. Network-Aware Downstream Penalty
        cost_downstream = self._compute_downstream_penalty(
            intersection_snap.intersection_id, phase, duration, network_state
        )

        # 7. Emergency Priority
        cost_emergency = 0.0
        duration_factor = duration / 30.0
        for d in green_dirs:
            if intersection_snap.emergency_status.get(d, False):
                cost_emergency -= self.config.w_emergency * duration_factor

        for d in red_dirs:
            if intersection_snap.emergency_status.get(d, False):
                cost_emergency += 2.0 * self.config.w_emergency * duration_factor

        total_cost = (
            cost_queue
            + cost_wait
            + cost_congestion
            + reward_throughput
            + cost_switch
            + cost_downstream
            + cost_emergency
        )
        return total_cost

    def _compute_downstream_penalty(
        self,
        iid: str,
        phase: str,
        duration: int,
        network_state: NetworkTrafficState,
    ) -> float:
        """
        Penalizes releasing traffic toward congested downstream intersections.
        """
        downstream_targets = DOWNSTREAM_TOPOLOGY.get(iid, {}).get(phase, [])
        if not downstream_targets:
            return 0.0

        max_downstream_congestion = 0.0
        for target_id in downstream_targets:
            if target_id in network_state.intersections:
                target_snap = network_state.intersections[target_id]
                target_dirs = ("E", "W") if phase == "EW" else ("N", "S")
                target_density = sum(
                    target_snap.densities.get(d, 0.0) for d in target_dirs
                ) / max(1.0, float(len(target_dirs)))
                max_downstream_congestion = max(max_downstream_congestion, target_density)

        if max_downstream_congestion > 0.4:
            normalized_penalty = (max_downstream_congestion - 0.4) * (duration / 90.0)
            return self.config.w_downstream * normalized_penalty
        return 0.0

    def compute_cross_intersection_coupling(
        self,
        snap_u: IntersectionStateSnapshot,
        phase_u: str,
        dur_u: int,
        snap_v: IntersectionStateSnapshot,
        phase_v: str,
        dur_v: int,
    ) -> float:
        """
        Computes quadratic interaction penalty between adjacent intersections.
        Reward for coordinated green waves (both EW on horizontal arterial),
        penalty for conflicting orthogonal discharge.
        """
        u_id = snap_u.intersection_id
        v_id = snap_v.intersection_id

        is_neighbor = (
            v_id in DOWNSTREAM_TOPOLOGY.get(u_id, {}).get("EW", [])
            or v_id in DOWNSTREAM_TOPOLOGY.get(u_id, {}).get("NS", [])
        )
        if not is_neighbor:
            return 0.0

        if phase_u == phase_v:
            # Coordination reward for synchronized arterial green
            return -0.5 * self.config.w_downstream * (dur_u * dur_v / 8100.0)
        else:
            # Phase conflict penalty
            return 0.5 * self.config.w_downstream * (dur_u * dur_v / 8100.0)
