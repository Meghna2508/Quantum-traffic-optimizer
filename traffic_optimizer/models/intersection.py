"""Intersection model representing signalized traffic junctions."""

from dataclasses import dataclass, field
from typing import Dict, Optional
from traffic_optimizer.config import (
    SignalPhase,
    Direction,
    DEFAULT_ROAD_CAPACITY,
    ALLOWED_GREEN_DURATIONS,
)


@dataclass
class Intersection:
    """
    Represents an urban signalized intersection.

    Attributes:
        intersection_id: Unique intersection identifier (e.g., 'I1').
        connected_roads: Mapping from approach direction ('N', 'S', 'E', 'W') to road ID.
        queue_lengths: Vehicles in queue for each approach direction.
        traffic_densities: Traffic density (0.0 to 1.0) for each approach direction.
        road_capacities: Maximum vehicle capacity for each approach direction.
        current_phase: Current active signal phase (SignalPhase.NORTH_SOUTH or SignalPhase.EAST_WEST).
        current_green_duration: Active green duration in seconds (must be 30, 60, or 90).
        emergency_status: Boolean flag per direction indicating emergency vehicle presence.
    """
    intersection_id: str
    connected_roads: Dict[str, str] = field(
        default_factory=lambda: {d.value: "" for d in Direction}
    )
    queue_lengths: Dict[str, int] = field(
        default_factory=lambda: {d.value: 0 for d in Direction}
    )
    traffic_densities: Dict[str, float] = field(
        default_factory=lambda: {d.value: 0.0 for d in Direction}
    )
    road_capacities: Dict[str, int] = field(
        default_factory=lambda: {d.value: DEFAULT_ROAD_CAPACITY for d in Direction}
    )
    current_phase: SignalPhase = SignalPhase.NORTH_SOUTH
    current_green_duration: int = 30
    emergency_status: Dict[str, bool] = field(
        default_factory=lambda: {d.value: False for d in Direction}
    )

    def set_signal_decision(self, phase: SignalPhase, duration: int) -> None:
        """
        Updates the active signal phase and discrete green duration.

        Args:
            phase: SignalPhase enum (NORTH_SOUTH or EAST_WEST).
            duration: Discrete green duration (must be in ALLOWED_GREEN_DURATIONS).
        """
        if duration not in ALLOWED_GREEN_DURATIONS:
            raise ValueError(
                f"Invalid green duration: {duration}. Must be one of {ALLOWED_GREEN_DURATIONS}"
            )
        self.current_phase = phase
        self.current_green_duration = duration

    def set_queue_length(self, direction: str, queue_len: int) -> None:
        """Sets queue length for a given approach direction and updates traffic density."""
        if direction not in [d.value for d in Direction]:
            raise ValueError(f"Invalid direction: {direction}")
        cap = self.road_capacities.get(direction, DEFAULT_ROAD_CAPACITY)
        bounded_queue = max(0, min(queue_len, cap))
        self.queue_lengths[direction] = bounded_queue
        self.traffic_densities[direction] = round(bounded_queue / float(cap) if cap > 0 else 0.0, 4)

    def set_emergency_status(self, direction: str, has_emergency: bool) -> None:
        """Sets emergency status for a specific approach direction."""
        if direction not in [d.value for d in Direction]:
            raise ValueError(f"Invalid direction: {direction}")
        self.emergency_status[direction] = has_emergency

    @property
    def total_ns_queue(self) -> int:
        """Total queue count for North-South approaches."""
        return self.queue_lengths.get(Direction.NORTH.value, 0) + self.queue_lengths.get(Direction.SOUTH.value, 0)

    @property
    def total_ew_queue(self) -> int:
        """Total queue count for East-West approaches."""
        return self.queue_lengths.get(Direction.EAST.value, 0) + self.queue_lengths.get(Direction.WEST.value, 0)

    @property
    def has_emergency(self) -> bool:
        """Returns True if any approach has an emergency vehicle active."""
        return any(self.emergency_status.values())
