"""Unit tests for Intersection model."""

import pytest
from traffic_optimizer.config import SignalPhase, ALLOWED_GREEN_DURATIONS
from traffic_optimizer.models.intersection import Intersection


def test_intersection_creation():
    intersection = Intersection(intersection_id="I1")
    assert intersection.intersection_id == "I1"
    assert intersection.current_phase == SignalPhase.NORTH_SOUTH
    assert intersection.current_green_duration == 30
    assert intersection.queue_lengths["N"] == 0
    assert intersection.road_capacities["N"] == 100


def test_signal_phase_and_duration_changes():
    intersection = Intersection(intersection_id="I1")
    intersection.set_signal_decision(SignalPhase.EAST_WEST, 60)
    assert intersection.current_phase == SignalPhase.EAST_WEST
    assert intersection.current_green_duration == 60

    # Test invalid duration
    with pytest.raises(ValueError):
        intersection.set_signal_decision(SignalPhase.NORTH_SOUTH, 45)


def test_queue_and_density_updates():
    intersection = Intersection(intersection_id="I1")
    intersection.set_queue_length("N", 25)
    assert intersection.queue_lengths["N"] == 25
    assert intersection.traffic_densities["N"] == 0.25

    # Capacity overflow bound check
    intersection.set_queue_length("N", 150)
    assert intersection.queue_lengths["N"] == 100
    assert intersection.traffic_densities["N"] == 1.0


def test_emergency_status():
    intersection = Intersection(intersection_id="I1")
    assert not intersection.has_emergency
    intersection.set_emergency_status("S", True)
    assert intersection.has_emergency
    assert intersection.emergency_status["S"] is True
