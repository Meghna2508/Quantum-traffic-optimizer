"""Signal controller abstractions and classical baseline rule-based controller."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any

from traffic_optimizer.config import SignalPhase, ALLOWED_GREEN_DURATIONS
from traffic_optimizer.models.traffic_state import NetworkTrafficState, IntersectionStateSnapshot


@dataclass(frozen=True)
class SignalDecision:
    """
    Signal decision for a single intersection.

    Attributes:
        phase: Active signal phase (SignalPhase.NORTH_SOUTH or SignalPhase.EAST_WEST).
        duration: Green duration in seconds (must be in ALLOWED_GREEN_DURATIONS).
    """
    phase: SignalPhase
    duration: int

    def to_dict(self) -> Dict[str, Any]:
        """Converts decision to dictionary format."""
        return {
            "phase": self.phase.value,
            "duration": self.duration,
        }


class BaseSignalController(ABC):
    """
    Abstract base class for all signal controllers.

    Both classical adaptive controllers and future Quantum (QUBO/QAOA) controllers
    must implement this interface.
    """

    @abstractmethod
    def get_decisions(
        self, state: NetworkTrafficState
    ) -> Dict[str, SignalDecision]:
        """
        Calculates signal decisions for each intersection given a network state snapshot.

        Args:
            state: NetworkTrafficState immutable snapshot.

        Returns:
            Dictionary mapping intersection_id -> SignalDecision.
        """
        pass


class ClassicalRuleBasedController(BaseSignalController):
    """
    Rule-based classical adaptive traffic signal controller.

    Decision Rules:
    1. Emergency Override: If an emergency vehicle is present on an approach, immediately
       select the phase covering that direction.
    2. Demand Comparison: Calculate total queue count for North-South vs East-West.
       Select the phase with the higher demand.
    3. Discrete Duration Selection:
       - Queue < 15: 30 seconds
       - 15 <= Queue <= 35: 60 seconds
       - Queue > 35: 90 seconds
    """

    def get_decisions(
        self, state: NetworkTrafficState
    ) -> Dict[str, SignalDecision]:
        decisions: Dict[str, SignalDecision] = {}

        for iid, snap in state.intersections.items():
            decision = self._compute_intersection_decision(snap)
            decisions[iid] = decision

        return decisions

    def _compute_intersection_decision(
        self, snap: IntersectionStateSnapshot
    ) -> SignalDecision:
        ns_queue = snap.queue_lengths.get("N", 0) + snap.queue_lengths.get("S", 0)
        ew_queue = snap.queue_lengths.get("E", 0) + snap.queue_lengths.get("W", 0)

        ns_emergency = snap.emergency_status.get("N", False) or snap.emergency_status.get("S", False)
        ew_emergency = snap.emergency_status.get("E", False) or snap.emergency_status.get("W", False)

        # Rule 1: Emergency prioritization
        if ns_emergency and not ew_emergency:
            selected_phase = SignalPhase.NORTH_SOUTH
            max_queue = ns_queue
        elif ew_emergency and not ns_emergency:
            selected_phase = SignalPhase.EAST_WEST
            max_queue = ew_queue
        # Rule 2: Compare NS vs EW queue demand
        elif ns_queue >= ew_queue:
            selected_phase = SignalPhase.NORTH_SOUTH
            max_queue = ns_queue
        else:
            selected_phase = SignalPhase.EAST_WEST
            max_queue = ew_queue

        # Rule 3: Map queue demand to discrete green duration (30, 60, 90 seconds)
        if max_queue < 15:
            duration = ALLOWED_GREEN_DURATIONS[0]  # 30s
        elif max_queue <= 35:
            duration = ALLOWED_GREEN_DURATIONS[1]  # 60s
        else:
            duration = ALLOWED_GREEN_DURATIONS[2]  # 90s

        return SignalDecision(phase=selected_phase, duration=duration)
