import traci


INTERSECTIONS = [
    "I1", "I2", "I3", "I4",
    "I5", "I6", "I7", "I8"
]


cumulative_throughput = 0


def get_traffic_metrics():

    global cumulative_throughput

    vehicles = traci.vehicle.getIDList()

    vehicle_count = len(vehicles)

    total_waiting_time = 0
    total_fuel = 0
    total_co2 = 0

    for vehicle_id in vehicles:

        total_waiting_time += traci.vehicle.getWaitingTime(
            vehicle_id
        )

        total_fuel += traci.vehicle.getFuelConsumption(
            vehicle_id
        )

        total_co2 += traci.vehicle.getCO2Emission(
            vehicle_id
        )

    queue_lengths = {}

    for intersection in INTERSECTIONS:

        try:
            controlled_lanes = traci.trafficlight.getControlledLanes(
                intersection
            )
        except traci.TraCIException:
            queue_lengths[intersection] = 0
            continue

        queue = 0

        for lane in set(controlled_lanes):

            vehicle_ids = traci.lane.getLastStepVehicleIDs(
                lane
            )

            for vehicle_id in vehicle_ids:

                speed = traci.vehicle.getSpeed(
                    vehicle_id
                )

                if speed < 0.5:
                    queue += 1

        queue_lengths[intersection] = queue

    arrived_this_step = traci.simulation.getArrivedNumber()

    cumulative_throughput += arrived_this_step

    return {
        "vehicle_count": vehicle_count,
        "total_waiting_time": total_waiting_time,
        "queue_lengths": queue_lengths,
        "throughput": cumulative_throughput,
        "fuel_consumption": total_fuel,
        "co2_emission": total_co2
    }
