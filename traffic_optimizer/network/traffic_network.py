"""NetworkX-based traffic network model representing intersections and connected roads."""

from typing import Dict, List, Optional
import networkx as nx

from traffic_optimizer.config import Direction, DEFAULT_ROAD_CAPACITY, SignalPhase
from traffic_optimizer.models.intersection import Intersection
from traffic_optimizer.models.road import Road
from traffic_optimizer.models.traffic_state import (
    IntersectionStateSnapshot,
    NetworkTrafficState,
)


class TrafficNetwork:
    """
    Manages the urban traffic topology using NetworkX DiGraph.

    Nodes represent Intersections; directed edges represent Roads.
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.intersections: Dict[str, Intersection] = {}
        self.roads: Dict[str, Road] = {}

    def add_intersection(self, intersection: Intersection) -> None:
        """Adds an intersection node to the network."""
        self.intersections[intersection.intersection_id] = intersection
        self.graph.add_node(intersection.intersection_id, obj=intersection)

    def add_road(self, road: Road) -> None:
        """Adds a directed road edge connecting source to destination intersection."""
        if road.source_id not in self.intersections or road.dest_id not in self.intersections:
            raise ValueError(
                f"Source ({road.source_id}) or Dest ({road.dest_id}) must exist in network first."
            )
        self.roads[road.road_id] = road
        self.graph.add_edge(
            road.source_id,
            road.dest_id,
            key=road.road_id,
            road=road,
            capacity=road.capacity,
        )

    def get_intersection(self, intersection_id: str) -> Intersection:
        """Retrieves intersection object by ID."""
        if intersection_id not in self.intersections:
            raise KeyError(f"Intersection {intersection_id} not found in network.")
        return self.intersections[intersection_id]

    def get_road(self, road_id: str) -> Road:
        """Retrieves road object by ID."""
        if road_id not in self.roads:
            raise KeyError(f"Road {road_id} not found in network.")
        return self.roads[road_id]

    def get_state_snapshot(self, timestamp: float = 0.0) -> NetworkTrafficState:
        """
        Extracts a clean, immutable snapshot of the current network state.

        Returns:
            NetworkTrafficState snapshot object.
        """
        intersection_snapshots: Dict[str, IntersectionStateSnapshot] = {}

        for iid, intersection in self.intersections.items():
            snapshot = IntersectionStateSnapshot(
                intersection_id=iid,
                queue_lengths=dict(intersection.queue_lengths),
                densities=dict(intersection.traffic_densities),
                capacities=dict(intersection.road_capacities),
                current_phase=intersection.current_phase.value,
                current_green_duration=intersection.current_green_duration,
                emergency_status=dict(intersection.emergency_status),
            )
            intersection_snapshots[iid] = snapshot

        road_counts = {rid: road.current_vehicle_count for rid, road in self.roads.items()}

        return NetworkTrafficState(
            timestamp=timestamp,
            intersections=intersection_snapshots,
            road_vehicle_counts=road_counts,
        )

    @classmethod
    def create_grid_network(
        cls, rows: int = 2, cols: int = 2, default_capacity: int = DEFAULT_ROAD_CAPACITY
    ) -> "TrafficNetwork":
        """
        Factory method creating a grid network topology with `rows` x `cols` intersections.

        Default 2x2 grid produces 4 connected intersections (I1 to I4):
        I1 (0,0) <---> I2 (0,1)
          ^              ^
          |              |
          v              v
        I3 (1,0) <---> I4 (1,1)

        Scales seamlessly to 8 intersections (2x4 grid: I1..I8).
        """
        net = cls()
        node_grid: Dict[tuple, str] = {}

        # 1. Create Intersections
        idx = 1
        for r in range(rows):
            for c in range(cols):
                iid = f"I{idx}"
                node_grid[(r, c)] = iid
                intersection = Intersection(
                    intersection_id=iid,
                    road_capacities={d.value: default_capacity for d in Direction},
                )
                net.add_intersection(intersection)
                idx += 1

        # 2. Connect Adjacent Intersections with Bidirectional Roads
        for (r, c), u_id in node_grid.items():
            u_intersection = net.get_intersection(u_id)

            # North neighbor (row r-1, col c)
            if r > 0:
                v_id = node_grid[(r - 1, c)]
                r_id = f"R_{u_id}_{v_id}"
                net.add_road(Road(road_id=r_id, source_id=u_id, dest_id=v_id, capacity=default_capacity))
                u_intersection.connected_roads[Direction.NORTH.value] = r_id

            # South neighbor (row r+1, col c)
            if r < rows - 1:
                v_id = node_grid[(r + 1, c)]
                r_id = f"R_{u_id}_{v_id}"
                net.add_road(Road(road_id=r_id, source_id=u_id, dest_id=v_id, capacity=default_capacity))
                u_intersection.connected_roads[Direction.SOUTH.value] = r_id

            # East neighbor (row r, col c+1)
            if c < cols - 1:
                v_id = node_grid[(r, c + 1)]
                r_id = f"R_{u_id}_{v_id}"
                net.add_road(Road(road_id=r_id, source_id=u_id, dest_id=v_id, capacity=default_capacity))
                u_intersection.connected_roads[Direction.EAST.value] = r_id

            # West neighbor (row r, col c-1)
            if c > 0:
                v_id = node_grid[(r, c - 1)]
                r_id = f"R_{u_id}_{v_id}"
                net.add_road(Road(road_id=r_id, source_id=u_id, dest_id=v_id, capacity=default_capacity))
                u_intersection.connected_roads[Direction.WEST.value] = r_id

        return net
