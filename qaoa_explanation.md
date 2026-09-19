# Quantum Approximate Optimization Algorithm (QAOA) Guide

This document provides a beginner-friendly yet technically rigorous explanation of the **QAOA Quantum Engine** implemented for **Quantum-Enhanced Adaptive Urban Traffic Optimization**.

---

## 1. What a Qubit Represents in This Project
In our traffic optimization project, each **qubit** corresponds to a single binary decision variable $x(i, p, d) \in \{0, 1\}$.
- $|0\rangle$: Candidate configuration is **not selected** ($x = 0$).
- $|1\rangle$: Candidate configuration **is selected** ($x = 1$).

For a 4-intersection network with 6 candidates per junction, we use **24 qubits** ($4 \times 6 = 24$).

---

## 2. What Superposition Means in Optimization Search
Classically, a computer evaluates one traffic signal configuration at a time.
In quantum computing, applying Hadamard gates $H^{\otimes N}$ puts all $N$ qubits into an equal **superposition state**:
$$|\psi_0\rangle = \frac{1}{\sqrt{2^N}} \sum_{x \in \{0,1\}^N} |x\rangle$$

This means the quantum state simultaneously contains non-zero probability amplitudes for **all $2^N$ possible signal combinations** ($2^{24} = 16,777,216$ states for 4 intersections) before measurement!

---

## 3. Why QUBO Needs to Be Converted to an Ising Formulation
Quantum hardware and QAOA circuits operate natively on physical quantum spins (Pauli-Z matrices $Z_i$).
To execute QUBO objectives on quantum gates, we map binary variables $x_i \in \{0, 1\}$ to Pauli-Z spin operators $Z_i \in \{+1, -1\}$ using:
$$x_i = \frac{1 - Z_i}{2}$$

This transformation preserves exact energy equivalence:
$$C(x) \equiv H_{\text{Ising}}(Z(x)) = \sum_{i} h_i Z_i + \sum_{i < j} J_{ij} Z_i Z_j + \text{Ising\_Offset}$$

---

## 4. What the Cost Hamiltonian ($H_C$) Does
The **Cost Hamiltonian** $H_C = \sum h_i Z_i + \sum J_{ij} Z_i Z_j$ encodes the traffic optimization objective and constraint penalties into the quantum system's energy landscape.

Applying the unitary operator $U(H_C, \gamma) = e^{-i \gamma H_C}$:
- Adds quantum phase shifts proportional to the QUBO cost of each state.
- High-cost states acquire rapid phase shifts, while low-cost states stay in phase.

---

## 5. What the Mixer Hamiltonian ($H_M$) Does
The **Mixer Hamiltonian** $H_M = \sum_{i=1}^N X_i$ applies transverse Pauli-X magnetic fields:
$$U(H_M, \beta) = e^{-i \beta H_M} = \prod_{i=1}^N RX(2\beta)$$

The mixer acts as a quantum driver that rotates qubit states between $|0\rangle$ and $|1\rangle$, allowing quantum interference to redistribute probability amplitudes across the computational basis states.

---

## 6. What Gamma ($\gamma$) Does
$\gamma$ controls the duration and intensity of the **Cost Hamiltonian** rotation. It determines how strongly traffic queue costs, delay penalties, and emergency priorities shape the quantum state's phase.

---

## 7. What Beta ($\beta$) Does
$\beta$ controls the duration of the **Mixer Hamiltonian** rotation. It dictates how much quantum tunneling and state mixing occurs between candidate configurations.

---

## 8. What a QAOA Layer ($p$) Means
A **QAOA layer** $p$ consists of repeating the alternating sequence of Cost Unitary and Mixer Unitary:
$$|\psi(\vec{\gamma}, \vec{\beta})\rangle = U(H_M, \beta_p) U(H_C, \gamma_p) \cdots U(H_M, \beta_1) U(H_C, \gamma_1) |\psi_0\rangle$$

- $p = 1$: Single layer (shallow circuit, fast, suitable for noisy simulation).
- Higher $p$: Deeper circuit with greater variational expressiveness to approximate the ground state.

---

## 9. How Classical Optimization Tunes Gamma and Beta
QAOA is a **hybrid quantum-classical algorithm**:
1. Quantum Simulator executes circuit for current $(\vec{\gamma}, \vec{\beta})$.
2. Quantum Measurement returns sampled bitstrings and calculates expectation value $\langle H_C \rangle$.
3. Classical Optimizer (COBYLA / Nelder-Mead) updates $(\vec{\gamma}, \vec{\beta})$ to minimize $\langle H_C \rangle$.
4. Process iterates until convergence.

---

## 10. How Measurement Produces Bitstrings
When the final optimized quantum circuit $|\psi(\vec{\gamma}_{opt}, \vec{\beta}_{opt})\rangle$ is measured $S$ times (`shots=1024`), the quantum superposition collapses into classical bitstrings $x \in \{0, 1\}^N$ with probability $P(x) = |\langle x | \psi \rangle|^2$.

---

## 11. How Bitstrings Become Traffic Signal Decisions
`TrafficQUBODecoder` maps the 24-bit binary vector back into signal commands:
```python
"010000000100100000000001"
  │      │      │      └─► I4: (EW, 90s)
  │      │      └────────► I3: (NS, 30s)
  │      └───────────────► I2: (EW, 30s)
  └──────────────────────► I1: (NS, 60s)
```

---

## 12. Why QAOA is Approximate
Unlike classical brute-force search, QAOA does not search through all combinations sequentially. It uses quantum interference to construct a variational trial state whose energy approximates the ground state. For finite depth $p$, it produces a high-probability sample of near-optimal solutions.

---

## 13. Why QAOA Does NOT Guarantee the Global Optimum Every Run
1. **Finite Shots**: Sampling $S=1024$ times out of $16.7$ million states is a stochastic sampling process.
2. **Barren Plateaus & Local Optima**: Classical parameter optimization over $(\vec{\gamma}, \vec{\beta})$ can land in local minima.
3. **Finite Depth $p$**: Low layer count ($p=1$) limits state expressiveness.

*Crucially, our solver re-evaluates all sampled candidates against the exact QUBO matrix to select the best feasible solution observed.*

---

## 14. Why Aer Simulation is Used Instead of Real Quantum Hardware
- **Zero Queue Times**: Real NISQ devices have hours of cloud queue wait times.
- **Noise Control**: Aer provides exact statevector & shot-based simulation without hardware decoherence or gate errors.
- **Portability**: Runs locally on standard laptop hardware.

---

## Worked Numerical Example (2 Binary Variables)

Suppose we have 2 candidate variables $x_0$ and $x_1$ with QUBO cost:
$$C(x_0, x_1) = 2 x_0 + 4 x_1 + 8 x_0 x_1 + 3$$

### 1. Ising Conversion:
$$x_i = \frac{1 - Z_i}{2} \implies H(Z_0, Z_1) = -3 Z_0 - 4 Z_1 + 2 Z_0 Z_1 + 8$$

### 2. State Evaluation:
- State $|00\rangle \implies Z_0=+1, Z_1=+1 \implies C = 3$ (Global Optimum!)
- State $|10\rangle \implies Z_0=-1, Z_1=+1 \implies C = 5$
- State $|01\rangle \implies Z_0=+1, Z_1=-1 \implies C = 7$
- State $|11\rangle \implies Z_0=-1, Z_1=-1 \implies C = 17$

### 3. QAOA Optimization:
Hadamard gates initialize state $\frac{1}{2}(|00\rangle + |10\rangle + |01\rangle + |11\rangle)$.
Applying $U(H_C, \gamma)$ rotates $|00\rangle$ with the smallest phase, while $U(H_M, \beta)$ constructively interferes probability into state $|00\rangle$.
Upon measurement, bitstring `"00"` appears with the highest sampling frequency!
