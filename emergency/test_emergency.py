import traci

from green_corridor import (
    GreenCorridor,
    create_emergency_event
)


def run_emergency_demo():

    traci.start([
        "sumo",
        "-c",
        "sumo/simulation.sumocfg"
    ])

    corridor = GreenCorridor()

    emergency = create_emergency_event()

    print()
    print("=" * 60)
    print("EMERGENCY GREEN CORRIDOR DEMO")
    print("=" * 60)

    try:

        emergency_start_time = None

        for step in range(200):

            traci.simulationStep()

            # Trigger emergency at step 60
            if step == 60:

                print()
                print(
                    "🚑 EMERGENCY DETECTED"
                )

                emergency_start_time = (
                    traci.simulation.getTime()
                )

                corridor.set_route(
                    emergency["route"]
                )

                corridor.set_emergency_vehicle(
                    "ambulance_1"
                )

                corridor.activate()

                print(
                    "Green Corridor Activated"
                )

                print(
                    "Route:",
                    corridor.route
                )

                print(
                    "Intersections:",
                    corridor.route_intersections
                )

            # Restore normal traffic
            # after emergency priority period
            if step == 120:

                corridor.restore_normal_signals()

                emergency_end_time = (
                    traci.simulation.getTime()
                )

                if emergency_start_time is not None:

                    travel_time = (
                        emergency_end_time
                        - emergency_start_time
                    )

                    print()
                    print(
                        "Emergency priority completed"
                    )

                    print(
                        "Emergency travel time:",
                        travel_time,
                        "seconds"
                    )

        print()
        print(
            "Final Emergency Status:"
        )

        print(
            corridor.get_status()
        )

    finally:

        traci.close()


if __name__ == "__main__":

    run_emergency_demo()