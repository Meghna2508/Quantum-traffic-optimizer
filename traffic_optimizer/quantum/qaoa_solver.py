"""QAOA solver implementation using Qiskit and Qiskit Aer local simulation."""

import time
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
from scipy.optimize import minimize

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from traffic_optimizer.optimization.qubo import QUBOProblem
from traffic_optimizer.quantum.ising_converter import IsingConverter, IsingHamiltonian
from traffic_optimizer.quantum.result import QAOAResult


class QAOASolver:
    """
    Executes the Quantum Approximate Optimization Algorithm (QAOA) on a local Qiskit Aer simulator.

    QAOA Pipeline:
    1. QUBO -> Ising Hamiltonian Conversion (x_i = (1 - Z_i)/2).
    2. Initial State Preparation: Uniform superposition |+>^N via Hadamard gates.
    3. QAOA Circuit Construction: p layers of U(H_C, gamma) and U(H_M, beta).
    4. Classical Parameter Optimization: Uses SciPy optimizer (COBYLA/Nelder-Mead) to tune gamma and beta.
    5. Measurement & Re-indexing: Reverses Qiskit little-endian measurement keys to match QUBO index order.
    6. Candidate Evaluation & Feasibility Filtering: Selects lowest QUBO cost feasible candidate.
    """

    def __init__(
        self,
        p_layers: int = 1,
        shots: int = 1024,
        optimizer_name: str = "COBYLA",
        maxiter: int = 40,
        seed: int = 42,
    ) -> None:
        self.p_layers = p_layers
        self.shots = shots
        self.optimizer_name = optimizer_name
        self.maxiter = maxiter
        self.seed = seed

    def solve(self, qubo_problem: QUBOProblem) -> QAOAResult:
        """
        Executes QAOA parameter optimization and solution sampling for a given QUBOProblem.

        Args:
            qubo_problem: QUBOProblem instance.

        Returns:
            QAOAResult instance.
        """
        start_time = time.time()
        num_qubits = qubo_problem.num_variables

        # 1. Convert QUBO to Ising Hamiltonian
        ising = IsingConverter.qubo_to_ising(qubo_problem)

        # 2. Instantiate Qiskit Aer Simulator
        backend = AerSimulator(seed_simulator=self.seed)

        # 3. Initial Gamma and Beta parameters
        rng = np.random.RandomState(self.seed)
        initial_params = np.concatenate([
            rng.uniform(0.0, np.pi, self.p_layers),        # gamma_0 .. gamma_{p-1}
            rng.uniform(0.0, 0.5 * np.pi, self.p_layers),  # beta_0 .. beta_{p-1}
        ])

        # 4. Parameter Optimization Objective Function
        def objective_function(params: np.ndarray) -> float:
            gamma = params[: self.p_layers]
            beta = params[self.p_layers :]

            circuit = self.build_qaoa_circuit(ising, gamma, beta)
            circuit.measure_all()

            # Transpile / run on Aer simulator
            job = backend.run(circuit, shots=self.shots)
            result = job.result()
            counts = result.get_counts()

            # Compute expectation value of QUBO cost
            total_cost = 0.0
            total_shots = sum(counts.values())

            for qiskit_bitstr, count in counts.items():
                qubo_bitstr = self.reverse_qiskit_bitstring(qiskit_bitstr)
                cost = qubo_problem.evaluate_cost(qubo_bitstr)
                total_cost += cost * count

            return total_cost / float(total_shots)

        # Execute Classical Parameter Optimization
        opt_res = minimize(
            objective_function,
            initial_params,
            method=self.optimizer_name,
            options={"maxiter": self.maxiter},
        )

        opt_params = opt_res.x
        opt_gamma = list(opt_params[: self.p_layers])
        opt_beta = list(opt_params[self.p_layers :])

        # 5. Execute Final Optimized Circuit
        final_circuit = self.build_qaoa_circuit(ising, opt_gamma, opt_beta)
        final_circuit.measure_all()

        job = backend.run(final_circuit, shots=self.shots)
        counts = job.result().get_counts()

        # Map Qiskit little-endian keys -> QUBO index ordered bitstrings
        qubo_counts: Dict[str, int] = {}
        for qiskit_bitstr, count in counts.items():
            qubo_bitstr = self.reverse_qiskit_bitstring(qiskit_bitstr)
            qubo_counts[qubo_bitstr] = count

        # 6. Solution Selection & Feasibility Checking
        selected_bitstr, min_cost, is_feasible, is_fallback, fallback_reason = (
            self._select_best_feasible_solution(qubo_counts, qubo_problem)
        )

        elapsed_time = time.time() - start_time

        return QAOAResult(
            selected_bitstring=selected_bitstr,
            qubo_cost=round(min_cost, 4),
            is_feasible=is_feasible,
            shots=self.shots,
            p_layers=self.p_layers,
            optimal_gamma=[round(g, 4) for g in opt_gamma],
            optimal_beta=[round(b, 4) for b in opt_beta],
            backend_name="aer_simulator",
            execution_time_seconds=round(elapsed_time, 4),
            is_fallback=is_fallback,
            fallback_reason=fallback_reason,
            sampled_bitstring_counts=qubo_counts,
            metadata={
                "opt_fun_val": round(opt_res.fun, 4) if hasattr(opt_res, "fun") else 0.0,
                "opt_iterations": getattr(opt_res, "nfev", 0),
            },
        )

    def build_qaoa_circuit(
        self, ising: IsingHamiltonian, gamma: List[float], beta: List[float]
    ) -> QuantumCircuit:
        """
        Constructs the QAOA ansatz quantum circuit for p layers.

        Args:
            ising: IsingHamiltonian formulation.
            gamma: List of gamma parameters per layer.
            beta: List of beta parameters per layer.

        Returns:
            QuantumCircuit: Qiskit quantum circuit.
        """
        N = ising.num_qubits
        qc = QuantumCircuit(N)

        # 1. Initial State: Uniform superposition |+>^N via Hadamard gates
        for i in range(N):
            qc.h(i)

        # 2. QAOA Layers
        for l in range(self.p_layers):
            g_l = gamma[l]
            b_l = beta[l]

            # Cost Hamiltonian Unitary U(H_C, gamma_l)
            # Single-qubit Pauli-Z terms: exp(-i * gamma_l * h_i * Z_i) = RZ(2 * gamma_l * h_i)
            for i, h_i in ising.linear_z.items():
                qc.rz(2.0 * g_l * h_i, i)

            # Two-qubit Pauli-ZZ interaction terms: exp(-i * gamma_l * J_ij * Z_i Z_j) = RZZ(2 * gamma_l * J_ij)
            for (i, j), J_ij in ising.quadratic_zz.items():
                qc.rzz(2.0 * g_l * J_ij, i, j)

            # Mixer Hamiltonian Unitary U(H_M, beta_l)
            # Transverse field X-mixer: exp(-i * beta_l * X_i) = RX(2 * beta_l)
            for i in range(N):
                qc.rx(2.0 * b_l, i)

        return qc

    @staticmethod
    def reverse_qiskit_bitstring(qiskit_bitstring: str) -> str:
        """
        Converts Qiskit right-to-left little-endian bitstrings to QUBO index order.

        Qiskit measurement outputs format qubit q[0] at the rightmost string position.
        Reversing string maps index 0 back to position 0.
        """
        return qiskit_bitstring[::-1]

    def _select_best_feasible_solution(
        self, sampled_counts: Dict[str, int], qubo_problem: QUBOProblem
    ) -> Tuple[str, float, bool, bool, Optional[str]]:
        """
        Evaluates sampled candidate bitstrings using the ORIGINAL QUBO cost and selects
        the best feasible candidate.
        """
        best_feasible_bitstr = None
        best_feasible_cost = float("inf")

        best_any_bitstr = None
        best_any_cost = float("inf")

        for bitstr in sampled_counts.keys():
            cost = qubo_problem.evaluate_cost(bitstr)
            feasible = self.check_feasibility(bitstr, qubo_problem)

            if cost < best_any_cost:
                best_any_cost = cost
                best_any_bitstr = bitstr

            if feasible and cost < best_feasible_cost:
                best_feasible_cost = cost
                best_feasible_bitstr = bitstr

        if best_feasible_bitstr is not None:
            return best_feasible_bitstr, best_feasible_cost, True, False, None

        # Fallback Strategy if no sampled bitstring satisfied exactly-one constraint
        fallback_bitstr = self._generate_classical_fallback_bitstring(qubo_problem)
        fallback_cost = qubo_problem.evaluate_cost(fallback_bitstr)
        reason = "No feasible 1-hot candidate observed in QAOA measurement samples. Activated classical fallback."
        return fallback_bitstr, fallback_cost, True, True, reason

    @staticmethod
    def check_feasibility(bitstring: str, qubo_problem: QUBOProblem) -> bool:
        """
        Verifies if bitstring satisfies the exactly-one constraint per intersection.
        """
        x = [int(b) for b in bitstring]
        groups = qubo_problem.metadata.get("intersection_var_groups", {})

        for iid, group in groups.items():
            active_count = sum(x[idx] for idx in group)
            if active_count != 1:
                return False
        return True

    @staticmethod
    def _generate_classical_fallback_bitstring(qubo_problem: QUBOProblem) -> str:
        """
        Generates a valid 1-hot bitstring by picking the candidate with the lowest diagonal cost per group.
        """
        bit_list = [0] * qubo_problem.num_variables
        groups = qubo_problem.metadata.get("intersection_var_groups", {})

        for iid, group in groups.items():
            best_idx = min(
                group, key=lambda idx: qubo_problem.Q_matrix.get((idx, idx), 0.0)
            )
            bit_list[best_idx] = 1

        return "".join(str(b) for b in bit_list)
