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

        Args:
            state: NetworkTrafficState snapshot.

        Returns:
            Dict[str, SignalDecision]: Intersection decisions.
        """
        # 1. Build QUBO matrix from current traffic state
        qubo_problem = self.qubo_builder.build_qubo(state)

        # 2. Execute QAOA solver on Qiskit Aer
        self.last_result = self.solver.solve(qubo_problem)

        # 3. Decode best feasible bitstring into SignalDecision objects
        decisions = TrafficQUBODecoder.decode(
            self.last_result.selected_bitstring, qubo_problem
        )

        return decisions
