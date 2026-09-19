"""Unit tests for Road model."""

import pytest
from traffic_optimizer.models.road import Road


def test_road_creation():
    road = Road(road_id="R_I1_I2", source_id="I1", dest_id="I2", capacity=50)
    assert road.road_id == "R_I1_I2"
    assert road.source_id == "I1"
    assert road.dest_id == "I2"
    assert road.capacity == 50
    assert road.current_vehicle_count == 0
    assert road.queue_length == 0
    assert road.occupancy_rate == 0.0


def test_add_and_remove_vehicles_capacity_bound():
    road = Road(road_id="R1", source_id="I1", dest_id="I2", capacity=20)
    added = road.add_vehicles(15)
    assert added == 15
    assert road.current_vehicle_count == 15
    assert road.occupancy_rate == 0.75

    # Over-capacity addition
    added_extra = road.add_vehicles(10)
    assert added_extra == 5
    assert road.current_vehicle_count == 20
    assert road.occupancy_rate == 1.0

    # Discharge vehicles
    removed = road.remove_vehicles(8)
    assert removed == 8
    assert road.current_vehicle_count == 12
    assert road.occupancy_rate == 0.6
