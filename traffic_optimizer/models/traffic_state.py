"""Traffic State Snapshot module providing clean state representations for quantum and classical optimizers."""

from dataclasses import dataclass, field
from typing import Dict, Any
from traffic_optimizer.config import SignalPhase


@dataclass(frozen=True)
class IntersectionStateSnapshot:
    """
    Immutable snapshot of a single intersection's traffic state.

    Attributes:
        intersection_id: Intersection ID.
        queue_lengths: Queue length per direction {'N': int, 'S': int, 'E': int, 'W': int}.
        densities: Density per direction {'N': float, 'S': float, 'E': float, 'W': float}.
        capacities: Capacity per direction {'N': int, 'S': int, 'E': int, 'W': int}.
        current_phase: SignalPhase enum or string ('NS' or 'EW').
        current_green_duration: Green signal duration in seconds (30, 60, 90).
        emergency_status: Emergency vehicle flag per direction {'N': bool, 'S': bool, 'E': bool, 'W': bool}.
    """
    intersection_id: str
    queue_lengths: Dict[str, int]
    densities: Dict[str, float]
    capacities: Dict[str, int]
    current_phase: str
    current_green_duration: int
    emergency_status: Dict[str, bool]
    waiting_times: Dict[str, float] = field(default_factory=lambda: {"N": 0.0, "S": 0.0, "E": 0.0, "W": 0.0})
    approach_speeds: Dict[str, float] = field(default_factory=lambda: {"N": 13.89, "S": 13.89, "E": 13.89, "W": 13.89})

    def to_dict(self) -> Dict[str, Any]:
        """Converts snapshot into a standard Python dictionary."""
        return {
            "intersection_id": self.intersection_id,
            "queue_lengths": dict(self.queue_lengths),
            "densities": dict(self.densities),
            "capacities": dict(self.capacities),
            "current_phase": self.current_phase,
            "current_green_duration": self.current_green_duration,
            "emergency_status": dict(self.emergency_status),
            "waiting_times": dict(self.waiting_times),
            "approach_speeds": dict(self.approach_speeds),
        }


@dataclass(frozen=True)
class NetworkTrafficState:
    """
    Immutable snapshot of the entire traffic network state.

    Attributes:
        timestamp: Simulation step timestamp.
        intersections: Dictionary mapping intersection_id -> IntersectionStateSnapshot.
        road_vehicle_counts: Dictionary mapping road_id -> vehicle_count.
    """
    timestamp: float
    intersections: Dict[str, IntersectionStateSnapshot]
    road_vehicle_counts: Dict[str, int] = field(default_factory=dict)

    def get_intersection(self, intersection_id: str) -> IntersectionStateSnapshot:
        """Retrieves snapshot for a specific intersection."""
        if intersection_id not in self.intersections:
            raise KeyError(f"Intersection {intersection_id} not found in state snapshot.")
        return self.intersections[intersection_id]

    def to_dict(self) -> Dict[str, Any]:
        """Converts entire network state into a nested dictionary."""
        return {
            "timestamp": self.timestamp,
            "intersections": {
                iid: snap.to_dict() for iid, snap in self.intersections.items()
            },
            "road_vehicle_counts": dict(self.road_vehicle_counts),
        }
