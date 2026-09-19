import traci


INTERSECTIONS = [
    "I1", "I2", "I3", "I4",
    "I5", "I6", "I7", "I8"
]


def get_traffic_metrics():

    vehicles = traci.vehicle.getIDList()
    vehicle_count = len(vehicles)

    total_waiting_time = 0
    total_fuel = 0
    total_co2 = 0

    for vehicle_id in vehicles:
        total_waiting_time += traci.vehicle.getWaitingTime(vehicle_id)

        total_fuel += traci.vehicle.getFuelConsumption(vehicle_id)

        total_co2 += traci.vehicle.getCO2Emission(vehicle_id)

    queue_lengths = {}

    for intersection in INTERSECTIONS:

        controlled_lanes = traci.trafficlight.getControlledLanes(
            intersection
        )

        queue = 0

        for lane in set(controlled_lanes):

            vehicle_ids = traci.lane.getLastStepVehicleIDs(lane)

            for vehicle_id in vehicle_ids:

                speed = traci.vehicle.getSpeed(vehicle_id)

                if speed < 0.5:
                    queue += 1

        queue_lengths[intersection] = queue

    return {
        "vehicle_count": vehicle_count,
        "total_waiting_time": total_waiting_time,
        "queue_lengths": queue_lengths,
        "fuel_consumption": total_fuel,
        "co2_emission": total_co2
    }
