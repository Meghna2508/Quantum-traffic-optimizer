"""Deterministic synthetic traffic simulator engine."""

import random
from typing import Dict, Optional

from traffic_optimizer.config import (
    DEFAULT_TIMESTEP_SECONDS,
    DEFAULT_DISCHARGE_RATE,
    SignalPhase,
    Direction,
)
from traffic_optimizer.controllers.signal_controller import BaseSignalController
from traffic_optimizer.models.traffic_state import NetworkTrafficState
from traffic_optimizer.network.traffic_network import TrafficNetwork


class TrafficSimulator:
    """
    Simulates traffic demand, queue accumulation on RED phases,
    queue discharge on GREEN phases, and signal timing updates.

    Attributes:
        network: TrafficNetwork model instance.
        controller: BaseSignalController implementation.
        seed: Random seed for deterministic simulation.
        timestep: Simulation step length in seconds (default 5s).
        arrival_rate_max: Max vehicles arriving per approach per step.
        discharge_rate: Vehicle discharge rate per second during green.
    """

    def __init__(
        self,
        network: TrafficNetwork,
        controller: BaseSignalController,
        seed: int = 42,
        timestep: int = DEFAULT_TIMESTEP_SECONDS,
        arrival_rate_min: int = 1,
        arrival_rate_max: int = 4,
        discharge_rate: int = DEFAULT_DISCHARGE_RATE,
    ) -> None:
        self.network = network
        self.controller = controller
        self.rng = random.Random(seed)
        self.timestep = timestep
        self.arrival_rate_min = arrival_rate_min
        self.arrival_rate_max = arrival_rate_max
        self.discharge_rate = discharge_rate
        self.current_time = 0.0
        self.step_count = 0

        # Remaining green signal timer for each intersection (seconds)
        self.remaining_green_timers: Dict[str, int] = {
            iid: intersection.current_green_duration
            for iid, intersection in self.network.intersections.items()
        }

    def step(self) -> NetworkTrafficState:
        """
        Executes a single simulation step of `self.timestep` seconds.

        Steps:
        1. Query controller for new decisions if an intersection's green timer expires.
        2. Generate synthetic vehicle arrivals per approach direction.
        3. Discharge queues on active GREEN phases.
        4. Accumulate queues on active RED phases.
        5. Update timers and return state snapshot.

        Returns:
            NetworkTrafficState: Updated network state snapshot.
        """
        current_state = self.network.get_state_snapshot(self.current_time)

        # 1. Update Controller Decisions if signal timers expired
        decisions = self.controller.get_decisions(current_state)

        for iid, intersection in self.network.intersections.items():
            self.remaining_green_timers[iid] -= self.timestep

            # If green duration expired or initial step, apply new decision
            if self.remaining_green_timers[iid] <= 0:
                decision = decisions[iid]
                intersection.set_signal_decision(decision.phase, decision.duration)
                self.remaining_green_timers[iid] = decision.duration

        # 2. Simulate Traffic Dynamics for each intersection
        for iid, intersection in self.network.intersections.items():
            active_phase = intersection.current_phase

            for direction_enum in Direction:
                direction = direction_enum.value
                current_queue = intersection.queue_lengths[direction]

                # Generate synthetic arrivals
                arrivals = self.rng.randint(self.arrival_rate_min, self.arrival_rate_max)

                # Determine if approach has GREEN signal
                is_green = (
                    (direction in ("N", "S") and active_phase == SignalPhase.NORTH_SOUTH)
                    or (direction in ("E", "W") and active_phase == SignalPhase.EAST_WEST)
                )

                if is_green:
                    # Discharge rate * timestep seconds
                    potential_discharge = self.discharge_rate * self.timestep
                    net_change = arrivals - potential_discharge
                    new_queue = max(0, current_queue + net_change)
                else:
                    # Accumulate on RED
                    new_queue = current_queue + arrivals

                intersection.set_queue_length(direction, new_queue)

        # 3. Advance Simulation Time
        self.current_time += self.timestep
        self.step_count += 1

        return self.network.get_state_snapshot(self.current_time)
