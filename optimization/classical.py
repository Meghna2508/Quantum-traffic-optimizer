from itertools import product

from qubo import (
    INTERSECTIONS,
    create_traffic_costs,
    build_qubo_matrix,
    evaluate_solution
)


def generate_all_solutions():

    """
    Generate every possible binary signal configuration.

    For 8 intersections:

        2^8 = 256 solutions
    """

    number_of_variables = len(
        INTERSECTIONS
    )

    return list(
        product(
            [0, 1],
            repeat=number_of_variables
        )
    )


def solve_qubo_classically(
    traffic_state,
    emergency_data=None
):

    """
    Find the lowest-cost QUBO solution
    using exhaustive classical search.
    """

    solutions = generate_all_solutions()

    best_solution = None
    best_cost = float("inf")

    for solution in solutions:

        cost = evaluate_solution(
            solution,
            traffic_state,
            emergency_data
        )

        if cost < best_cost:

            best_cost = cost
            best_solution = solution

    return list(best_solution), best_cost


def convert_solution_to_signals(
    solution
):

    """
    Convert binary solution into
    readable signal decisions.
    """

    signal_plan = {}

    for index, decision in enumerate(
        solution
    ):

        intersection = INTERSECTIONS[index]

        if decision == 0:

            direction = "north_south"

        else:

            direction = "east_west"

        signal_plan[intersection] = {
            "decision": decision,
            "direction": direction
        }

    return signal_plan


def calculate_solution_details(
    solution,
    traffic_state,
    emergency_data=None
):

    """
    Return individual intersection costs.
    """

    costs = create_traffic_costs(
        traffic_state,
        emergency_data
    )

    details = {}

    for index, decision in enumerate(
        solution
    ):

        intersection = INTERSECTIONS[index]

        details[intersection] = {
            "decision": decision,
            "direction": (
                "north_south"
                if decision == 0
                else "east_west"
            ),
            "cost": costs[
                intersection
            ][decision]
        }

    return details


def run_classical_optimizer(
    traffic_state,
    emergency_data=None
):

    """
    Complete classical optimization pipeline.
    """

    solution, cost = solve_qubo_classically(
        traffic_state,
        emergency_data
    )

    signal_plan = convert_solution_to_signals(
        solution
    )

    details = calculate_solution_details(
        solution,
        traffic_state,
        emergency_data
    )

    return {
        "solution": solution,
        "bitstring": "".join(
            str(bit)
            for bit in solution
        ),
        "cost": cost,
        "signal_plan": signal_plan,
        "details": details
    }


if __name__ == "__main__":

    traffic_state = {

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

    print("=" * 60)
    print("CLASSICAL QUBO OPTIMIZER")
    print("=" * 60)

    print()
    print("Number of possible solutions:")

    solutions = generate_all_solutions()

    print(len(solutions))

    print()
    print("Running classical optimization...")

    result = run_classical_optimizer(
        traffic_state
    )

    print()
    print("Best Bitstring:")
    print(result["bitstring"])

    print()
    print("Best Cost:")
    print(f"{result['cost']:.4f}")

    print()
    print("Optimized Signal Plan:")
    print()

    for intersection, plan in result[
        "signal_plan"
    ].items():

        print(
            f"{intersection}: "
            f"{plan['direction']}"
        )

    print()
    print("Intersection Details:")
    print()

    for intersection, details in result[
        "details"
    ].items():

        print(
            f"{intersection}: "
            f"{details['direction']} "
            f"(cost={details['cost']:.4f})"
        )

    print()
    print("Classical optimization complete.")