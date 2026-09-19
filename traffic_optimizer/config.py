from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class SignalPhase(str, Enum):
    """Signal phase configuration."""
    NORTH_SOUTH = "NS"
    EAST_WEST = "EW"


class Direction(str, Enum):
    """Approach directions for intersections."""
    NORTH = "N"
    SOUTH = "S"
    EAST = "E"
    WEST = "W"


# Discrete green signal durations in seconds
ALLOWED_GREEN_DURATIONS: Tuple[int, ...] = (30, 60, 90)

# Default operational parameters
DEFAULT_ROAD_CAPACITY: int = 100
DEFAULT_DISCHARGE_RATE: int = 1  # vehicles per second under green phase
DEFAULT_TIMESTEP_SECONDS: int = 5  # simulation timestep duration


@dataclass
class QUBOConfig:
    """
    Configurable weights and penalty parameters for the normalized multi-objective QUBO formulation.
    All terms use finite, explicit, and configurable weights.

    Parameters:
        lambda_penalty: Penalty weight enforcing exactly-one configuration per junction (dimensionless). Default: 1000.0.
        w_queue: Weight for normalized remaining unserved queue on green approaches (dimensionless, [0, 1]). Default: 10.0.
        w_wait: Weight for normalized waiting delay on red approaches (dimensionless, [0, 2]). Default: 8.0.
        w_congestion: Weight for normalized approach saturation ratio (dimensionless, [0, 1]). Default: 5.0.
        w_throughput: Reward weight for normalized vehicle discharge throughput (dimensionless, [0, 1], subtracted). Default: 12.0.
        w_emergency: Overwhelming priority weight for emergency vehicle clearance (dimensionless). Default: 500.0.
        w_downstream: Penalty weight for discharging traffic toward congested downstream approaches (dimensionless). Default: 8.0.
        w_switch: Penalty weight for toggling signal phase away from current active phase (dimensionless). Default: 4.0.
    """
    lambda_penalty: float = 1000.0
    w_queue: float = 10.0
    w_wait: float = 8.0
    w_congestion: float = 5.0
    w_throughput: float = 12.0
    w_emergency: float = 500.0
    w_downstream: float = 8.0
    w_switch: float = 1.5


