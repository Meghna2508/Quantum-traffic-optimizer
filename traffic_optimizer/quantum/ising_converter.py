"""Ising Hamiltonian converter mapping QUBO problem representation into Pauli-Z operators."""

from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Union
import numpy as np

from traffic_optimizer.optimization.qubo import QUBOProblem


@dataclass
class IsingHamiltonian:
    r"""
    Mathematical representation of an Ising Spin Hamiltonian:
        H(Z) = \sum_i h_i Z_i + \sum_{i < j} J_{ij} Z_i Z_j + offset

    where Z_i \in {+1, -1} is the Pauli-Z spin operator for qubit i.
    Binary variable mapping: x_i = (1 - Z_i) / 2.

    Attributes:
        num_qubits: Total number of qubits (equal to number of binary variables).
        linear_z: Dict mapping qubit index i -> single-qubit Z coefficient h_i.
        quadratic_zz: Dict mapping qubit pair (i, j) -> two-qubit Z_i Z_j interaction coefficient J_{ij}.
        offset: Scalar energy offset constant.
    """
    num_qubits: int
    linear_z: Dict[int, float] = field(default_factory=dict)
    quadratic_zz: Dict[Tuple[int, int], float] = field(default_factory=dict)
    offset: float = 0.0

    def evaluate_energy(self, bitstring: Union[str, List[int], np.ndarray]) -> float:
        r"""
        Evaluates Ising energy H(Z) for a given binary bitstring.

        Binary bitstring x_i \in {0, 1} is mapped to Z_i = 1 - 2*x_i \in {+1, -1}.

        Args:
            bitstring: String of '0's and '1's or list of binary ints.

        Returns:
            float: Evaluated Ising energy.
        """
        if isinstance(bitstring, str):
            x = np.array([int(b) for b in bitstring], dtype=float)
        else:
            x = np.array(bitstring, dtype=float)

        if len(x) != self.num_qubits:
            raise ValueError(
                f"Bitstring length {len(x)} does not match num_qubits {self.num_qubits}."
            )

        # Spin transformation: x=0 -> Z=+1, x=1 -> Z=-1
        z = 1.0 - 2.0 * x

        energy = self.offset
        for i, h_i in self.linear_z.items():
            energy += h_i * z[i]

        for (i, j), J_ij in self.quadratic_zz.items():
            energy += J_ij * z[i] * z[j]

        return float(energy)


class IsingConverter:
    r"""
    Converts a QUBOProblem into an IsingHamiltonian.

    Transformation rules:
        x_i = (1 - Z_i) / 2
        Q_{ii} x_i = (Q_{ii}/2) - (Q_{ii}/2) Z_i
        Q_{ij} x_i x_j = (Q_{ij}/4) - (Q_{ij}/4) Z_i - (Q_{ij}/4) Z_j + (Q_{ij}/4) Z_i Z_j

    Yields exact equivalence: C(x) == H_Ising(Z(x)) for all x \in {0, 1}^N.
    """

    @staticmethod
    def qubo_to_ising(qubo: QUBOProblem) -> IsingHamiltonian:
        """
        Converts a QUBOProblem instance into an IsingHamiltonian.

        Args:
            qubo: QUBOProblem instance.

        Returns:
            IsingHamiltonian instance.
        """
        num_qubits = qubo.num_variables
        linear_z: Dict[int, float] = {i: 0.0 for i in range(num_qubits)}
        quadratic_zz: Dict[Tuple[int, int], float] = {}
        offset = qubo.constant_offset

        for (i, j), coeff in qubo.Q_matrix.items():
            if i == j:
                # Diagonal linear QUBO term: Q_{ii} x_i
                offset += coeff / 2.0
                linear_z[i] -= coeff / 2.0
            else:
                # Off-diagonal quadratic QUBO term: Q_{ij} x_i x_j (i < j)
                pair = (min(i, j), max(i, j))
                offset += coeff / 4.0
                linear_z[pair[0]] -= coeff / 4.0
                linear_z[pair[1]] -= coeff / 4.0
                quadratic_zz[pair] = quadratic_zz.get(pair, 0.0) + (coeff / 4.0)

        # Round coefficients for clean floating-point precision
        linear_z = {i: round(val, 6) for i, val in linear_z.items() if abs(val) > 1e-9}
        quadratic_zz = {
            pair: round(val, 6) for pair, val in quadratic_zz.items() if abs(val) > 1e-9
        }
        offset = round(offset, 6)

        return IsingHamiltonian(
            num_qubits=num_qubits,
            linear_z=linear_z,
            quadratic_zz=quadratic_zz,
            offset=offset,
        )
