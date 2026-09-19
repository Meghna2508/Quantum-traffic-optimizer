import traci


INTERSECTIONS = [
    "I1", "I2", "I3", "I4",
    "I5", "I6", "I7", "I8"
]


class GreenCorridor:

    def __init__(self):

        self.previous_phases = {}

        self.active = False

        self.emergency_vehicle = None

        self.route = []

        self.route_intersections = []


    def detect_emergency_vehicle(self):

        vehicles = traci.vehicle.getIDList()

        for vehicle_id in vehicles:

            vehicle_type = traci.vehicle.getTypeID(
                vehicle_id
            )

            if (
                "emergency"
                in vehicle_type.lower()
            ):

                self.emergency_vehicle = vehicle_id

                return vehicle_id

        return None


    def set_emergency_vehicle(
        self,
        vehicle_id
    ):

        self.emergency_vehicle = vehicle_id

        return True


    def set_route(
        self,
        route
    ):

        self.route = route

        self.route_intersections = [
            intersection
            for intersection in route
            if intersection in INTERSECTIONS
        ]

        return self.route_intersections


    def save_current_signals(self):

        self.previous_phases = {}

        for intersection in self.route_intersections:

            try:

                self.previous_phases[
                    intersection
                ] = traci.trafficlight.getPhase(
                    intersection
                )

            except traci.TraCIException:

                continue


    def activate(self):

        if not self.route_intersections:

            return False

        self.save_current_signals()

        for intersection in self.route_intersections:

            try:

                # Phase 0 is used as the
                # emergency-priority phase
                # in the current SUMO prototype.

                traci.trafficlight.setPhase(
                    intersection,
                    0
                )

                traci.trafficlight.setPhaseDuration(
                    intersection,
                    60
                )

            except traci.TraCIException:

                continue

        self.active = True

        return True


    def restore_normal_signals(self):

        for intersection, phase in (
            self.previous_phases.items()
        ):

            try:

                traci.trafficlight.setPhase(
                    intersection,
                    phase
                )

                traci.trafficlight.setPhaseDuration(
                    intersection,
                    30
                )

            except traci.TraCIException:

                continue

        self.active = False

        return True


    def get_status(self):

        return {
            "active": self.active,
            "emergency_vehicle":
                self.emergency_vehicle,
            "route":
                self.route,
            "route_intersections":
                self.route_intersections
        }


def create_emergency_event():

    return {
        "type": "ambulance",
        "vehicle_id": None,
        "route": [
            "I1",
            "I2",
            "I3",
            "I4"
        ],
        "priority": "high"
    }


def calculate_emergency_travel_time(
    start_time,
    end_time
):

    return max(
        0,
        end_time - start_time
    )


if __name__ == "__main__":

    print("=" * 60)
    print("EMERGENCY GREEN CORRIDOR")
    print("=" * 60)

    emergency = create_emergency_event()

    print()
    print("Emergency Type:")
    print(
        emergency["type"]
    )

    print()
    print("Priority:")
    print(
        emergency["priority"]
    )

    print()
    print("Emergency Route:")

    for intersection in emergency[
        "route"
    ]:

        print(
            f"  {intersection}"
        )

    print()
    print(
        "Green Corridor module ready."
    )