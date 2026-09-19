"""Quantum Optimizer Controller inheriting from BaseSignalController."""

from typing import Dict, Optional
from traffic_optimizer.config import QUBOConfig
from traffic_optimizer.controllers.signal_controller import BaseSignalController, SignalDecision
from traffic_optimizer.models.traffic_state import NetworkTrafficState
from traffic_optimizer.optimization.qubo import TrafficQUBOBuilder, TrafficQUBODecoder
from traffic_optimizer.quantum.qaoa_solver import QAOASolver
from traffic_optimizer.quantum.result import QAOAResult


class QuantumOptimizerController(BaseSignalController):
    """
    Traffic signal controller powered by QAOA running on Qiskit Aer local simulation.

    Pipeline:
    NetworkTrafficState -> TrafficQUBOBuilder -> QUBO -> QAOASolver -> QAOAResult -> TrafficQUBODecoder -> SignalDecisions
    """

    def __init__(
        self,
        qubo_config: QUBOConfig = QUBOConfig(),
        p_layers: int = 1,
        shots: int = 1024,
        optimizer_name: str = "COBYLA",
        maxiter: int = 30,
        seed: int = 42,
    ) -> None:
        self.qubo_builder = TrafficQUBOBuilder(config=qubo_config)
        self.solver = QAOASolver(
            p_layers=p_layers,
            shots=shots,
            optimizer_name=optimizer_name,
            maxiter=maxiter,
            seed=seed,
        )
        self.last_result: Optional[QAOAResult] = None

    def get_decisions(
        self, state: NetworkTrafficState
    ) -> Dict[str, SignalDecision]:
        """
        Computes signal decisions for all intersections using QAOA.
        Partitions large networks into groups of at most 3 intersections (<= 18 qubits)
        to prevent feasibility collapse and statevector simulation memory limits.

        Args:
            state: NetworkTrafficState snapshot.

        Returns:
            Dict[str, SignalDecision]: Intersection decisions.
        """
        intersection_ids = sorted(list(state.intersections.keys()))
        if not intersection_ids:
            return {}

        # Chunk into groups of at most 3 intersections (<= 18 qubits)
        chunk_size = 3
        groups = [
            intersection_ids[i : i + chunk_size]
            for i in range(0, len(intersection_ids), chunk_size)
        ]

        all_decisions: Dict[str, SignalDecision] = {}
        for group in groups:
            # 1. Build QUBO matrix for the current group
            qubo_problem = self.qubo_builder.build_qubo(
                state, target_intersection_ids=group
            )

            # 2. Execute QAOA solver on Qiskit Aer
            res = self.solver.solve(qubo_problem)
            self.last_result = res

            # 3. Decode best feasible bitstring into SignalDecision objects
            group_decisions = TrafficQUBODecoder.decode(
                res.selected_bitstring, qubo_problem
            )
            all_decisions.update(group_decisions)

        return all_decisions
