import traci


def get_traffic_density():

    density = {}

    for intersection in [
        "I1", "I2", "I3", "I4",
        "I5", "I6", "I7", "I8"
    ]:

        lanes = traci.trafficlight.getControlledLanes(intersection)

        total_vehicles = 0
        total_capacity = 0

        for lane in set(lanes):

            vehicle_count = traci.lane.getLastStepVehicleNumber(lane)
            lane_length = traci.lane.getLength(lane)

            total_vehicles += vehicle_count
            total_capacity += lane_length / 7.5

        if total_capacity > 0:
            density[intersection] = (
                total_vehicles / total_capacity
            )
        else:
            density[intersection] = 0

    return density