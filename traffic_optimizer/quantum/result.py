"""QAOA execution result dataclass and metadata representation."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class QAOAResult:
    """
    Structured result returned by the QAOASolver.

    Attributes:
        selected_bitstring: Best feasible binary solution string (in QUBO index order).
        qubo_cost: Total QUBO cost evaluated using the original QUBO matrix.
        is_feasible: True if the bitstring satisfies exactly-one constraints per intersection.
        shots: Number of measurement shots executed on the Aer backend.
        p_layers: Number of QAOA circuit layers (depth p).
        optimal_gamma: List of optimized gamma parameters for cost Hamiltonian layers [gamma_0 .. gamma_{p-1}].
        optimal_beta: List of optimized beta parameters for mixer Hamiltonian layers [beta_0 .. beta_{p-1}].
        backend_name: Name of the Qiskit execution backend or simulator used.
        execution_time_seconds: Wall-clock execution time of the QAOA run.
        is_fallback: True if a fallback strategy was activated due to infeasible sampling.
        fallback_reason: Optional explanation string if fallback was activated.
        sampled_bitstring_counts: Sampled measurement bitstring counts.
        metadata: Additional diagnostic information.
    """
    selected_bitstring: str
    qubo_cost: float
    is_feasible: bool
    shots: int
    p_layers: int
    optimal_gamma: List[float]
    optimal_beta: List[float]
    backend_name: str
    execution_time_seconds: float
    is_fallback: bool = False
    fallback_reason: Optional[str] = None
    sampled_bitstring_counts: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
