import traci
import sys
import os

sys.path.append(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "optimization"
    )
)

from qaoa import run_quantum_optimizer


INTERSECTIONS = [
    "I1", "I2", "I3", "I4",
    "I5", "I6", "I7", "I8"
]


def get_current_traffic_state():

    queue_lengths = {}
    density = {}

    for intersection in INTERSECTIONS:

        try:

            lanes = traci.trafficlight.getControlledLanes(
                intersection
            )

            queue = 0
            vehicles = 0
            capacity = 0

            for lane in set(lanes):

                vehicle_ids = (
                    traci.lane.getLastStepVehicleIDs(
                        lane
                    )
                )

                vehicles += len(vehicle_ids)

                for vehicle_id in vehicle_ids:

                    if traci.vehicle.getSpeed(
                        vehicle_id
                    ) < 0.5:

                        queue += 1

                lane_length = traci.lane.getLength(
                    lane
                )

                capacity += lane_length / 7.5

            queue_lengths[intersection] = queue

            if capacity > 0:
                density[intersection] = (
                    vehicles / capacity
                )
            else:
                density[intersection] = 0

        except traci.TraCIException:

            queue_lengths[intersection] = 0
            density[intersection] = 0

    return {
        "queue_lengths": queue_lengths,
        "density": density,
        "waiting_time": 0
    }


def close_road(edge_id):

    try:

        traci.edge.setDisallowed(
            edge_id,
            ["passenger"]
        )

        return True

    except traci.TraCIException:

        return False


def reopen_road(edge_id):

    try:

        traci.edge.setAllowed(
            edge_id,
            ["passenger"]
        )

        return True

    except traci.TraCIException:

        return False


def apply_signal_plan(signal_plan):

    applied = {}

    for intersection in INTERSECTIONS:

        if intersection not in signal_plan:
            continue

        decision = signal_plan[
            intersection
        ]["decision"]

        try:

            traci.trafficlight.setPhase(
                intersection,
                decision
            )

            traci.trafficlight.setPhaseDuration(
                intersection,
                30
            )

            applied[intersection] = decision

        except traci.TraCIException:

            applied[intersection] = None

    return applied


def run_accident_demo():

    traci.start([
        "sumo",
        "-c",
        "sumo/simulation.sumocfg"
    ])

    accident_edge = None
    accident_active = False

    try:

        for step in range(200):

            traci.simulationStep()

            # --------------------------------
            # ACCIDENT EVENT
            # --------------------------------

            if step == 60:

                print()
                print("=" * 60)
                print("🚧 ACCIDENT DETECTED")
                print("=" * 60)

                # Select an existing edge dynamically
                # so we don't depend on a hard-coded
                # edge name.

                edges = traci.edge.getIDList()

                if edges:

                    accident_edge = edges[
                        len(edges) // 2
                    ]

                    print(
                        "Road closed:",
                        accident_edge
                    )

                    if close_road(
                        accident_edge
                    ):

                        accident_active = True

                        print(
                            "Road closure applied."
                        )

                # Get changed traffic state
                traffic_state = (
                    get_current_traffic_state()
                )

                print()
                print(
                    "Traffic state recalculated."
                )

                # Re-run quantum optimizer
                result = run_quantum_optimizer(
                    traffic_state,
                    shots=512
                )

                print()
                print(
                    "Quantum re-optimization completed."
                )

                print(
                    "New bitstring:",
                    result["bitstring"]
                )

                print(
                    "New cost:",
                    result["cost"]
                )

                applied = apply_signal_plan(
                    result["signal_plan"]
                )

                print()
                print(
                    "New signal plan applied:"
                )

                for intersection, decision in (
                    applied.items()
                ):

                    print(
                        f"  {intersection}: "
                        f"phase {decision}"
                    )

            # --------------------------------
            # ROAD REOPEN
            # --------------------------------

            if step == 130 and accident_active:

                print()
                print("=" * 60)
                print("ROAD CLOSURE CLEARED")
                print("=" * 60)

                if reopen_road(
                    accident_edge
                ):

                    print(
                        "Road reopened:",
                        accident_edge
                    )

                accident_active = False

                # Recalculate traffic again
                traffic_state = (
                    get_current_traffic_state()
                )

                result = run_quantum_optimizer(
                    traffic_state,
                    shots=512
                )

                apply_signal_plan(
                    result["signal_plan"]
                )

                print(
                    "Traffic optimization restored."
                )

        print()
        print("=" * 60)
        print("ACCIDENT DEMO COMPLETED")
        print("=" * 60)

    finally:

        traci.close()


if __name__ == "__main__":

    run_accident_demo()