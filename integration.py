import sys
import os
import time
import traci


# ----------------------------------------
# PATHS
# ----------------------------------------

PROJECT_ROOT = os.path.dirname(
    os.path.abspath(__file__)
)

sys.path.append(
    os.path.join(
        PROJECT_ROOT,
        "simulation"
    )
)

sys.path.append(
    os.path.join(
        PROJECT_ROOT,
        "optimization"
    )
)


from state import get_traffic_state
from signals import (
    set_signal_phase,
    set_signal_duration,
    get_signal_states
)

from qaoa import run_quantum_optimizer


# ----------------------------------------
# INTERSECTIONS
# ----------------------------------------

INTERSECTIONS = [
    "I1", "I2", "I3", "I4",
    "I5", "I6", "I7", "I8"
]


# ----------------------------------------
# CONFIGURATION
# ----------------------------------------

SIMULATION_STEPS = 200

OPTIMIZATION_INTERVAL = 20

GREEN_DURATION = 30


# ----------------------------------------
# APPLY SIGNAL PLAN
# ----------------------------------------

def apply_signal_plan(signal_plan):

    applied = {}

    for intersection in INTERSECTIONS:

        if intersection not in signal_plan:

            continue

        decision = signal_plan[
            intersection
        ]["decision"]

        success = set_signal_phase(
            intersection,
            decision
        )

        if success:

            set_signal_duration(
                intersection,
                GREEN_DURATION
            )

        applied[intersection] = {
            "decision": decision,
            "success": success
        }

    return applied


# ----------------------------------------
# DISPLAY TRAFFIC STATE
# ----------------------------------------

def display_state(
    step,
    state
):

    print()
    print("=" * 60)

    print(
        f"SIMULATION STEP: {step}"
    )

    print("=" * 60)

    print(
        "Vehicles:",
        state["vehicle_count"]
    )

    print(
        "Waiting Time:",
        round(
            state["waiting_time"],
            2
        ),
        "seconds"
    )

    print(
        "Throughput:",
        state["throughput"]
    )

    print(
        "Fuel:",
        round(
            state["fuel_consumption"],
            2
        )
    )

    print(
        "CO2:",
        round(
            state["co2_emission"],
            2
        )
    )

    print()
    print("Intersection Data:")

    for intersection in INTERSECTIONS:

        print(
            f"{intersection}: "
            f"density="
            f"{state['density'][intersection]:.2f}, "
            f"queue="
            f"{state['queue_lengths'][intersection]}"
        )


# ----------------------------------------
# RUN INTEGRATED SYSTEM
# ----------------------------------------

def run_integrated_system():

    print()
    print("=" * 60)
    print(
        "QUANTUM-ENHANCED "
        "ADAPTIVE TRAFFIC OPTIMIZATION"
    )
    print("=" * 60)

    print()
    print(
        "Starting SUMO..."
    )

    traci.start([
        "sumo",
        "-c",
        "sumo/simulation.sumocfg"
    ])

    try:

        for step in range(
            SIMULATION_STEPS
        ):

            traci.simulationStep()

            # --------------------------------
            # GET CURRENT TRAFFIC STATE
            # --------------------------------

            state = get_traffic_state()

            # --------------------------------
            # DISPLAY STATE
            # --------------------------------

            if step % 20 == 0:

                display_state(
                    step,
                    state
                )

            # --------------------------------
            # QUANTUM OPTIMIZATION
            # --------------------------------

            if (
                step % OPTIMIZATION_INTERVAL
                == 0
            ):

                print()
                print(
                    "⚛️ Running QAOA optimization..."
                )

                result = (
                    run_quantum_optimizer(
                        state,
                        shots=512
                    )
                )

                print(
                    "Quantum bitstring:",
                    result["bitstring"]
                )

                print(
                    "Optimization cost:",
                    round(
                        result["cost"],
                        3
                    )
                )

                # --------------------------------
                # APPLY OPTIMIZED SIGNAL PLAN
                # --------------------------------

                applied = (
                    apply_signal_plan(
                        result["signal_plan"]
                    )
                )

                print()
                print(
                    "Optimized signal plan:"
                )

                for intersection in (
                    INTERSECTIONS
                ):

                    if (
                        intersection
                        in result["signal_plan"]
                    ):

                        direction = (
                            result[
                                "signal_plan"
                            ][intersection][
                                "direction"
                            ]
                        )

                        print(
                            f"  {intersection}: "
                            f"{direction}"
                        )

                print()
                print(
                    "Signal control applied."
                )

            time.sleep(0.02)

    finally:

        traci.close()

        print()
        print("=" * 60)
        print(
            "INTEGRATED SIMULATION COMPLETED"
        )
        print("=" * 60)


if __name__ == "__main__":

    run_integrated_system()