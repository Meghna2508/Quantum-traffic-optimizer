INTERSECTIONS = [
    "I1", "I2", "I3", "I4",
    "I5", "I6", "I7", "I8"
]

GREEN_TIMES = [30, 45, 60]

# Objective weights
WEIGHT_WAITING = 0.30
WEIGHT_QUEUE = 0.30
WEIGHT_CONGESTION = 0.20
WEIGHT_CAPACITY = 0.10
WEIGHT_EMERGENCY = 0.10


def create_signal_variables():
    """
    Create one binary variable for every intersection.

    0 -> North-South priority
    1 -> East-West priority
    """

    variables = {}

    for intersection in INTERSECTIONS:
        variables[intersection] = {
            0: "north_south",
            1: "east_west"
        }

    return variables


def create_decision_space():
    """
    Define possible signal decisions.
    """

    decision_space = {}

    for intersection in INTERSECTIONS:
        decision_space[intersection] = {
            "directions": {
                0: "north_south",
                1: "east_west"
            },
            "green_times": GREEN_TIMES
        }

    return decision_space


def calculate_waiting_cost(waiting_time):
    """
    Convert waiting time into a normalized cost.
    """

    return waiting_time / 100.0


def calculate_queue_cost(queue_length):
    """
    Convert queue length into a normalized cost.
    """

    return queue_length / 10.0


def calculate_congestion_cost(density):
    """
    Higher traffic density means higher congestion cost.
    """

    return density


def calculate_capacity_cost(queue_length, capacity):
    """
    Penalize traffic when queue approaches/exceeds capacity.
    """

    if capacity <= 0:
        return 0

    return queue_length / capacity


def calculate_emergency_cost(intersection, emergency_data):
    """
    Give emergency-route intersections special priority.

    Normal intersection -> 0
    Emergency intersection -> negative cost
    """

    if not emergency_data:
        return 0

    emergency_intersections = emergency_data.get(
        "intersections",
        []
    )

    if intersection in emergency_intersections:
        return -2.0

    return 0


def get_directional_values(traffic_state, intersection):
    """
    Get directional traffic values.

    If directional values are available, use them.

    Otherwise, estimate them from total intersection traffic
    so that the QUBO remains usable with the current SUMO state.
    """

    directional = traffic_state.get(
        "directional",
        {}
    )

    if intersection in directional:

        values = directional[intersection]

        return {
            "north_south": values.get(
                "north_south",
                {}
            ),
            "east_west": values.get(
                "east_west",
                {}
            )
        }

    density = traffic_state.get(
        "density",
        {}
    ).get(
        intersection,
        0
    )

    queue = traffic_state.get(
        "queue_lengths",
        {}
    ).get(
        intersection,
        0
    )

    waiting = traffic_state.get(
        "waiting_time",
        0
    )

    # Temporary directional estimate.
    # This will be replaced by real directional traffic
    # when directional lane data is added.
    north_south_factor = 0.60
    east_west_factor = 0.40

    return {
        "north_south": {
            "density": density * north_south_factor,
            "queue": queue * north_south_factor,
            "waiting": waiting * north_south_factor
        },
        "east_west": {
            "density": density * east_west_factor,
            "queue": queue * east_west_factor,
            "waiting": waiting * east_west_factor
        }
    }


def calculate_direction_cost(
    density,
    queue,
    waiting,
    capacity,
    emergency_cost=0
):
    """
    Calculate total cost for one signal direction.
    """

    waiting_cost = calculate_waiting_cost(
        waiting
    )

    queue_cost = calculate_queue_cost(
        queue
    )

    congestion_cost = calculate_congestion_cost(
        density
    )

    capacity_cost = calculate_capacity_cost(
        queue,
        capacity
    )

    total_cost = (
        WEIGHT_WAITING * waiting_cost
        + WEIGHT_QUEUE * queue_cost
        + WEIGHT_CONGESTION * congestion_cost
        + WEIGHT_CAPACITY * capacity_cost
        + WEIGHT_EMERGENCY * emergency_cost
    )

    return total_cost


def create_traffic_costs(
    traffic_state,
    emergency_data=None
):
    """
    Convert current traffic state into signal decision costs.
    """

    costs = {}

    for intersection in INTERSECTIONS:

        directions = get_directional_values(
            traffic_state,
            intersection
        )

        queue = traffic_state.get(
            "queue_lengths",
            {}
        ).get(
            intersection,
            0
        )

        capacity = max(
            queue + 1,
            1
        )

        emergency_cost = calculate_emergency_cost(
            intersection,
            emergency_data
        )

        ns = directions["north_south"]
        ew = directions["east_west"]

        north_south_cost = calculate_direction_cost(
            ns["density"],
            ns["queue"],
            ns["waiting"],
            capacity,
            emergency_cost
        )

        east_west_cost = calculate_direction_cost(
            ew["density"],
            ew["queue"],
            ew["waiting"],
            capacity,
            emergency_cost
        )

        costs[intersection] = {
            0: north_south_cost,
            1: east_west_cost
        }

    return costs


def calculate_waiting_objective(traffic_state):

    objective = {}

    for intersection in INTERSECTIONS:

        directions = get_directional_values(
            traffic_state,
            intersection
        )

        objective[intersection] = {
            0: calculate_waiting_cost(
                directions["north_south"]["waiting"]
            ),
            1: calculate_waiting_cost(
                directions["east_west"]["waiting"]
            )
        }

    return objective


def calculate_queue_objective(traffic_state):

    objective = {}

    for intersection in INTERSECTIONS:

        directions = get_directional_values(
            traffic_state,
            intersection
        )

        objective[intersection] = {
            0: calculate_queue_cost(
                directions["north_south"]["queue"]
            ),
            1: calculate_queue_cost(
                directions["east_west"]["queue"]
            )
        }

    return objective


def calculate_congestion_objective(traffic_state):

    objective = {}

    for intersection in INTERSECTIONS:

        directions = get_directional_values(
            traffic_state,
            intersection
        )

        objective[intersection] = {
            0: calculate_congestion_cost(
                directions["north_south"]["density"]
            ),
            1: calculate_congestion_cost(
                directions["east_west"]["density"]
            )
        }

    return objective


def build_qubo(
    traffic_state,
    emergency_data=None
):
    """
    Build the QUBO model.

    QUBO form:

        Q(x) = sum(q_i * x_i)

    where x_i is a binary signal decision.
    """

    costs = create_traffic_costs(
        traffic_state,
        emergency_data
    )

    qubo = {}

    for index, intersection in enumerate(
        INTERSECTIONS
    ):

        variable = f"x{index}"

        north_south_cost = costs[
            intersection
        ][0]

        east_west_cost = costs[
            intersection
        ][1]

        # If x = 0:
        # North-South is selected.
        #
        # If x = 1:
        # East-West is selected.
        #
        # Therefore:
        #
        # cost = NS + (EW - NS)x

        qubo[(variable, variable)] = (
            east_west_cost
            - north_south_cost
        )

    return qubo


def build_qubo_matrix(
    traffic_state,
    emergency_data=None
):
    """
    Create an 8 x 8 QUBO matrix.
    """

    costs = create_traffic_costs(
        traffic_state,
        emergency_data
    )

    size = len(INTERSECTIONS)

    matrix = [
        [0.0 for _ in range(size)]
        for _ in range(size)
    ]

    for i, intersection in enumerate(
        INTERSECTIONS
    ):

        ns_cost = costs[
            intersection
        ][0]

        ew_cost = costs[
            intersection
        ][1]

        matrix[i][i] = (
            ew_cost - ns_cost
        )

    return matrix


def evaluate_solution(
    solution,
    traffic_state,
    emergency_data=None
):
    """
    Calculate the cost of a binary solution.

    Example:

        [0, 1, 0, 1, ...]

    0 -> North-South
    1 -> East-West
    """

    costs = create_traffic_costs(
        traffic_state,
        emergency_data
    )

    total_cost = 0

    for index, decision in enumerate(
        solution
    ):

        intersection = INTERSECTIONS[index]

        total_cost += costs[
            intersection
        ][decision]

    return total_cost


if __name__ == "__main__":

    sample_traffic_state = {

        "density": {
            "I1": 0.8,
            "I2": 0.5,
            "I3": 0.3,
            "I4": 0.7,
            "I5": 0.4,
            "I6": 0.9,
            "I7": 0.6,
            "I8": 0.2
        },

        "queue_lengths": {
            "I1": 10,
            "I2": 6,
            "I3": 3,
            "I4": 8,
            "I5": 5,
            "I6": 12,
            "I7": 7,
            "I8": 2
        },

        "waiting_time": 120
    }

    print("=" * 50)
    print("QUANTUM TRAFFIC OPTIMIZATION - QUBO")
    print("=" * 50)

    print()
    print("Signal Variables")
    print()

    variables = create_signal_variables()

    for intersection, decisions in variables.items():

        print(
            f"{intersection}: "
            f"0 = {decisions[0]}, "
            f"1 = {decisions[1]}"
        )

    print()
    print("Traffic Costs")
    print()

    costs = create_traffic_costs(
        sample_traffic_state
    )

    for intersection, values in costs.items():

        print(
            f"{intersection}: "
            f"N-S={values[0]:.3f}, "
            f"E-W={values[1]:.3f}"
        )

    print()
    print("QUBO Matrix")
    print()

    matrix = build_qubo_matrix(
        sample_traffic_state
    )

    for row in matrix:
        print(
            " ".join(
                f"{value:7.3f}"
                for value in row
            )
        )

    print()
    print("Example Solution")

    example_solution = [
        0, 1, 0, 1,
        0, 1, 0, 1
    ]

    cost = evaluate_solution(
        example_solution,
        sample_traffic_state
    )

    print(
        "Bitstring:",
        "".join(
            str(bit)
            for bit in example_solution
        )
    )

    print(
        f"Cost: {cost:.3f}"
    )

    print()
    print("QUBO generation complete.")