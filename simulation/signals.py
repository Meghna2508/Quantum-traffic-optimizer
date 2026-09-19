import traci

INTERSECTIONS = [
    "I1", "I2", "I3", "I4",
    "I5", "I6", "I7", "I8"
]


def get_signal_states():
    states = {}

    for intersection in INTERSECTIONS:
        try:
            states[intersection] = traci.trafficlight.getRedYellowGreenState(
                intersection
            )
        except traci.TraCIException:
            states[intersection] = "N/A"

    return states