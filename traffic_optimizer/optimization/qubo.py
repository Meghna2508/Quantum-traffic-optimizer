"""QUBO builder, QUBO matrix representation, and bitstring decoder for traffic signal optimization."""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Union, Optional
import numpy as np

from traffic_optimizer.config import (
    QUBOConfig,
    SignalPhase,
    ALLOWED_GREEN_DURATIONS,
)
from traffic_optimizer.models.traffic_state import NetworkTrafficState
from traffic_optimizer.optimization.cost_model import TrafficCostModel


@dataclass
class QUBOProblem:
    r"""
    Mathematical representation of the QUBO optimization problem.

    Standard QUBO Formulation:
        C(x) = x^T Q x + constant_offset
             = \sum_{i} Q_{ii} x_i + \sum_{i < j} Q_{ij} x_i x_j + constant_offset

    Attributes:
        num_variables: Total number of binary variables.
        var_names: List of variable string labels (e.g., 'x(I1,NS,30)').
        var_map: Dict mapping variable label -> integer index (0 to num_variables - 1).
        index_to_var: Dict mapping integer index -> variable label.
        Q_matrix: Dictionary mapping (i, j) index tuple -> coefficient float (with i <= j).
        constant_offset: Constant scalar offset resulting from penalty expansion.
        metadata: Supplementary problem metadata (e.g., intersection variable groupings).
    """
    num_variables: int
    var_names: List[str]
    var_map: Dict[str, int]
    index_to_var: Dict[int, str]
    Q_matrix: Dict[Tuple[int, int], float] = field(default_factory=dict)
    constant_offset: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dense_matrix(self) -> np.ndarray:
        """Converts Q_matrix dictionary into a 2D NumPy array of shape (N, N)."""
        mat = np.zeros((self.num_variables, self.num_variables), dtype=float)
        for (i, j), coeff in self.Q_matrix.items():
            mat[i, j] = coeff
        return mat

    def evaluate_cost(self, bitstring: Union[str, List[int], np.ndarray]) -> float:
        """
        Evaluates total QUBO cost C(x) for a given binary state vector.

        Args:
            bitstring: String of '0's and '1's or list/array of binary ints.

        Returns:
            float: Total evaluated QUBO cost.
        """
        if isinstance(bitstring, str):
            x = np.array([int(b) for b in bitstring], dtype=float)
        else:
            x = np.array(bitstring, dtype=float)

        if len(x) != self.num_variables:
            raise ValueError(
                f"Bitstring length {len(x)} does not match number of variables {self.num_variables}."
            )

        cost = self.constant_offset
        for (i, j), coeff in self.Q_matrix.items():
            if i == j:
                cost += coeff * x[i]
            else:
                cost += coeff * x[i] * x[j]
        return float(cost)


class TrafficQUBOBuilder:
    r"""
    Constructs the QUBO formulation from a NetworkTrafficState snapshot.

    For each intersection i, candidate configurations are:
      - (NS, 30), (NS, 60), (NS, 90)
      - (EW, 30), (EW, 60), (EW, 90)
    Giving 6 binary variables per intersection: x(i, p, d) in {0, 1}.

    Exactly-one constraint penalty per intersection:
      P_i = lambda * (1 - sum_k x_{i,k})^2
          = lambda - lambda * sum_k x_{i,k} + 2*lambda * sum_{k < m} x_{i,k} x_{i,m}
    """

    def __init__(
        self,
        config: QUBOConfig = QUBOConfig(),
        cost_model: TrafficCostModel = None,
    ) -> None:
        self.config = config
        self.cost_model = cost_model or TrafficCostModel(config=config)

    def build_qubo(
        self,
        network_state: NetworkTrafficState,
        target_intersection_ids: Optional[List[str]] = None,
    ) -> QUBOProblem:
        """
        Constructs the complete QUBO matrix and variable mappings.

        Args:
            network_state: NetworkTrafficState immutable state snapshot.
            target_intersection_ids: Optional subset of intersection IDs to optimize.

        Returns:
            QUBOProblem instance.
        """
        candidate_configs: List[Tuple[str, int]] = []
        for phase in [SignalPhase.NORTH_SOUTH.value, SignalPhase.EAST_WEST.value]:
            for dur in ALLOWED_GREEN_DURATIONS:
                candidate_configs.append((phase, dur))

        if target_intersection_ids is not None:
            intersection_ids = sorted([iid for iid in target_intersection_ids if iid in network_state.intersections])
        else:
            intersection_ids = sorted(list(network_state.intersections.keys()))
        var_names: List[str] = []
        var_map: Dict[str, int] = {}
        index_to_var: Dict[int, str] = {}
        intersection_var_groups: Dict[str, List[int]] = {}

        idx = 0
        for iid in intersection_ids:
            group: List[int] = []
            for phase, dur in candidate_configs:
                var_name = f"x({iid},{phase},{dur})"
                var_names.append(var_name)
                var_map[var_name] = idx
                index_to_var[idx] = var_name
                group.append(idx)
                idx += 1
            intersection_var_groups[iid] = group

        num_vars = idx
        Q_matrix: Dict[Tuple[int, int], float] = {}
        constant_offset = 0.0

        # 1. Linear terms and Exactly-One Penalty per intersection
        for iid, group in intersection_var_groups.items():
            snap = network_state.get_intersection(iid)

            # Penalty constant term offset: +lambda per intersection
            constant_offset += self.config.lambda_penalty

            # Diagonal linear coefficients Q_{k,k} = H_{i,k} - lambda
            for local_idx, global_idx in enumerate(group):
                phase, dur = candidate_configs[local_idx]

                # Compute traffic objective cost H_{i, p, d}
                h_cost = self.cost_model.compute_candidate_cost(
                    snap, phase, dur, network_state
                )

                # Combine with constraint linear term -lambda
                linear_coeff = h_cost - self.config.lambda_penalty
                Q_matrix[(global_idx, global_idx)] = round(linear_coeff, 6)

            # Quadratic off-diagonal penalty terms Q_{k,m} = +2 * lambda for distinct candidates
            for k_idx in range(len(group)):
                g_k = group[k_idx]
                for m_idx in range(k_idx + 1, len(group)):
                    g_m = group[m_idx]
                    pair = (min(g_k, g_m), max(g_k, g_m))
                    Q_matrix[pair] = round(2.0 * self.config.lambda_penalty, 6)

        # 2. Cross-Intersection Quadratic Coupling (Network interaction)
        for u_idx, u_id in enumerate(intersection_ids):
            snap_u = network_state.get_intersection(u_id)
            group_u = intersection_var_groups[u_id]

            for v_id in intersection_ids[u_idx + 1:]:
                snap_v = network_state.get_intersection(v_id)
                group_v = intersection_var_groups[v_id]

                for k_u, g_u in enumerate(group_u):
                    phase_u, dur_u = candidate_configs[k_u]
                    for k_v, g_v in enumerate(group_v):
                        phase_v, dur_v = candidate_configs[k_v]

                        coupling = self.cost_model.compute_cross_intersection_coupling(
                            snap_u, phase_u, dur_u, snap_v, phase_v, dur_v
                        )
                        if abs(coupling) > 1e-6:
                            pair = (min(g_u, g_v), max(g_u, g_v))
                            existing = Q_matrix.get(pair, 0.0)
                            Q_matrix[pair] = round(existing + coupling, 6)

        metadata = {
            "intersection_var_groups": intersection_var_groups,
            "candidate_configs": candidate_configs,
            "intersection_ids": intersection_ids,
        }

        return QUBOProblem(
            num_variables=num_vars,
            var_names=var_names,
            var_map=var_map,
            index_to_var=index_to_var,
            Q_matrix=Q_matrix,
            constant_offset=round(constant_offset, 6),
            metadata=metadata,
        )


class TrafficQUBODecoder:
    """
    Decodes solution bitstrings into SignalDecision dictionaries per intersection.
    """

    @staticmethod
    def decode(
        bitstring: Union[str, List[int], np.ndarray], qubo_problem: QUBOProblem
    ) -> Dict[str, Any]:
        """
        Converts a binary state solution into a dictionary of SignalDecision objects.

        Args:
            bitstring: Solution bitstring (e.g. '010000100000...') or binary list/array.
            qubo_problem: QUBOProblem containing variable metadata.

        Returns:
            Dict[str, SignalDecision]: Mapping intersection_id -> SignalDecision.
        """
        from traffic_optimizer.controllers.signal_controller import SignalDecision

        if isinstance(bitstring, str):
            x = [int(b) for b in bitstring]
        else:
            x = [int(b) for b in bitstring]

        if len(x) != qubo_problem.num_variables:
            raise ValueError(
                f"Bitstring length {len(x)} does not match QUBO num_variables {qubo_problem.num_variables}."
            )

        decisions: Dict[str, SignalDecision] = {}
        groups = qubo_problem.metadata["intersection_var_groups"]
        candidate_configs = qubo_problem.metadata["candidate_configs"]

        for iid, group in groups.items():
            selected_indices = [g_idx for g_idx in group if x[g_idx] == 1]

            if len(selected_indices) == 1:
                g_idx = selected_indices[0]
                local_idx = group.index(g_idx)
                phase_str, duration = candidate_configs[local_idx]
                phase = SignalPhase(phase_str)
                decisions[iid] = SignalDecision(phase=phase, duration=duration)
            elif len(selected_indices) == 0:
                # Fallback default if zero selected
                phase_str, duration = candidate_configs[0]
                decisions[iid] = SignalDecision(phase=SignalPhase(phase_str), duration=duration)
            else:
                # Fallback to first active selected configuration if multiple active
                g_idx = selected_indices[0]
                local_idx = group.index(g_idx)
                phase_str, duration = candidate_configs[local_idx]
                decisions[iid] = SignalDecision(phase=SignalPhase(phase_str), duration=duration)

        return decisions
