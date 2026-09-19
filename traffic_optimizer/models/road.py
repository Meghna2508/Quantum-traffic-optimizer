"""Road segment model representing directed traffic links between intersections."""

from dataclasses import dataclass
from traffic_optimizer.config import DEFAULT_ROAD_CAPACITY


@dataclass
class Road:
    """
    Represents a directed road connecting two intersections.

    Attributes:
        road_id: Unique identifier for the road link.
        source_id: Source intersection ID.
        dest_id: Destination intersection ID.
        capacity: Maximum vehicle capacity of the road segment.
        current_vehicle_count: Current number of vehicles on the road.
        queue_length: Number of vehicles waiting in queue at the downstream end.
        free_flow_speed: Free flow speed in km/h.
    """
    road_id: str
    source_id: str
    dest_id: str
    capacity: int = DEFAULT_ROAD_CAPACITY
    current_vehicle_count: int = 0
    queue_length: int = 0
    free_flow_speed: float = 50.0

    def add_vehicles(self, count: int) -> int:
        """
        Adds vehicles to the road up to its capacity.

        Returns:
            int: Number of vehicles successfully added.
        """
        if count < 0:
            raise ValueError("Vehicle count cannot be negative")
        space_left = max(0, self.capacity - self.current_vehicle_count)
        added = min(count, space_left)
        self.current_vehicle_count += added
        self.queue_length += added
        return added

    def remove_vehicles(self, count: int) -> int:
        """
        Removes vehicles from the queue and road vehicle count.

        Returns:
            int: Number of vehicles successfully discharged.
        """
        if count < 0:
            raise ValueError("Vehicle count cannot be negative")
        removed = min(count, self.queue_length, self.current_vehicle_count)
        self.queue_length -= removed
        self.current_vehicle_count -= removed
        return removed

    @property
    def occupancy_rate(self) -> float:
        """Returns traffic density ratio (0.0 to 1.0)."""
        if self.capacity <= 0:
            return 0.0
        return min(1.0, self.current_vehicle_count / float(self.capacity))
