import numpy as np

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from qubo import (
    INTERSECTIONS,
    create_traffic_costs,
    evaluate_solution
)


def create_cost_hamiltonian(
    traffic_state,
    emergency_data=None
):
    """
    Convert the QUBO signal costs into
    coefficients for a quantum cost Hamiltonian.

    Each intersection corresponds to one qubit.

    |0> -> North-South
    |1> -> East-West
    """

    costs = create_traffic_costs(
        traffic_state,
        emergency_data
    )

    coefficients = []

    for intersection in INTERSECTIONS:

        north_south_cost = costs[
            intersection
        ][0]

        east_west_cost = costs[
            intersection
        ][1]

        # Convert binary cost:
        #
        # C(x) = NS + (EW - NS)x
        #
        # into a Z-basis coefficient.

        constant = (
            north_south_cost
            + east_west_cost
        ) / 2

        z_coefficient = (
            north_south_cost
            - east_west_cost
        ) / 2

        coefficients.append({
            "intersection": intersection,
            "constant": constant,
            "z": z_coefficient
        })

    return coefficients


def create_qaoa_circuit(
    traffic_state,
    gamma=1.0,
    beta=0.5,
    emergency_data=None
):
    """
    Create a simple p=1 QAOA circuit.

    Steps:

    1. Put every qubit into superposition.
    2. Apply the cost Hamiltonian.
    3. Apply the mixing operation.
    4. Measure all qubits.
    """

    number_of_qubits = len(
        INTERSECTIONS
    )

    circuit = QuantumCircuit(
        number_of_qubits,
        number_of_qubits
    )

    coefficients = create_cost_hamiltonian(
        traffic_state,
        emergency_data
    )

    # Initial superposition
    for qubit in range(
        number_of_qubits
    ):

        circuit.h(qubit)

    # Cost layer
    for qubit, coefficient in enumerate(
        coefficients
    ):

        z_value = coefficient["z"]

        circuit.rz(
            2 * gamma * z_value,
            qubit
        )

    # Mixing layer
    for qubit in range(
        number_of_qubits
    ):

        circuit.rx(
            2 * beta,
            qubit
        )

    # Measurement
    circuit.measure(
        range(number_of_qubits),
        range(number_of_qubits)
    )

    return circuit


def run_qaoa(
    traffic_state,
    shots=2048,
    gamma=1.0,
    beta=0.5,
    emergency_data=None
):
    """
    Execute the QAOA circuit using
    the Qiskit Aer simulator.
    """

    circuit = create_qaoa_circuit(
        traffic_state,
        gamma,
        beta,
        emergency_data
    )

    simulator = AerSimulator()

    result = simulator.run(
        circuit,
        shots=shots
    ).result()

    counts = result.get_counts()

    return counts


def bitstring_to_solution(
    bitstring
):
    """
    Convert Qiskit's measured bitstring
    into the intersection decision order.

    Qiskit returns classical bits in
    reverse display order, so reverse it.
    """

    clean_bitstring = (
        bitstring
        .replace(" ", "")
    )

    clean_bitstring = clean_bitstring[
        ::-1
    ]

    return [
        int(bit)
        for bit in clean_bitstring
    ]


def find_best_quantum_solution(
    counts,
    traffic_state,
    emergency_data=None
):
    """
    Evaluate measured QAOA solutions
    and select the lowest-cost one.
    """

    best_solution = None
    best_cost = float("inf")
    best_bitstring = None

    for bitstring, frequency in counts.items():

        solution = bitstring_to_solution(
            bitstring
        )

        cost = evaluate_solution(
            solution,
            traffic_state,
            emergency_data
        )

        if cost < best_cost:

            best_cost = cost
            best_solution = solution
            best_bitstring = bitstring

    return {
        "solution": best_solution,
        "bitstring": best_bitstring,
        "cost": best_cost
    }


def convert_solution_to_signals(
    solution
):
    """
    Convert quantum binary solution
    into readable signal decisions.
    """

    signal_plan = {}

    for index, decision in enumerate(
        solution
    ):

        intersection = INTERSECTIONS[
            index
        ]

        if decision == 0:

            direction = "north_south"

        else:

            direction = "east_west"

        signal_plan[intersection] = {
            "decision": decision,
            "direction": direction
        }

    return signal_plan


def run_quantum_optimizer(
    traffic_state,
    shots=2048,
    gamma=1.0,
    beta=0.5,
    emergency_data=None
):
    """
    Complete QAOA optimization pipeline.
    """

    counts = run_qaoa(
        traffic_state,
        shots,
        gamma,
        beta,
        emergency_data
    )

    best = find_best_quantum_solution(
        counts,
        traffic_state,
        emergency_data
    )

    signal_plan = convert_solution_to_signals(
        best["solution"]
    )

    return {
        "counts": counts,
        "solution": best["solution"],
        "bitstring": best["bitstring"],
        "cost": best["cost"],
        "signal_plan": signal_plan
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
    print("QAOA QUANTUM TRAFFIC OPTIMIZER")
    print("=" * 60)

    print()
    print("Creating QAOA circuit...")

    circuit = create_qaoa_circuit(
        traffic_state
    )

    print(circuit)

    print()
    print("Running QAOA on Qiskit Aer...")

    result = run_quantum_optimizer(
        traffic_state
    )

    print()
    print("Measurement Results:")
    print(
        result["counts"]
    )

    print()
    print("Best Quantum Bitstring:")
    print(
        result["bitstring"]
    )

    print()
    print("Best Quantum Cost:")
    print(
        f"{result['cost']:.4f}"
    )

    print()
    print("Quantum Signal Plan:")
    print()

    for intersection, plan in result[
        "signal_plan"
    ].items():

        print(
            f"{intersection}: "
            f"{plan['direction']}"
        )

    print()
    print("QAOA optimization complete.")