# Mathematical QUBO Formulation for Urban Traffic Optimization

This document provides a mathematical explanation of the Quadratic Unconstrained Binary Optimization (QUBO) formulation designed for the **Quantum-Enhanced Adaptive Urban Traffic Optimization** project.

---

## 1. Binary Variable Representation

For each intersection $i \in \{1, \dots, N\}$, we define binary decision variables:
$$x_{i, p, d} \in \{0, 1\}$$

where:
- $i$: Intersection ID (e.g., `I1`, `I2`, ..., `IN`)
- $p$: Active signal phase $\in \{\text{NS}, \text{EW}\}$ ($\text{NS} = \text{North-South Green}$, $\text{EW} = \text{East-West Green}$)
- $d$: Discrete green duration $\in \{30, 60, 90\}$ seconds

$x_{i, p, d} = 1$ indicates that intersection $i$ selects configuration $(p, d)$.

---

## 2. Why Six Variables Per Intersection?

For any intersection, traffic signal control requires making two simultaneous discrete choices:
1. Which direction gets the green light ($\text{NS}$ or $\text{EW}$).
2. How long the green light stays active ($30\text{s}$, $60\text{s}$, or $90\text{s}$).

The Cartesian product of these discrete choices produces 6 candidate configurations:
$$\text{Candidates} = \{\text{NS}\}\times\{30, 60, 90\} \;\cup\; \{\text{EW}\}\times\{30, 60, 90\}$$
$$= \{(\text{NS},30), (\text{NS},60), (\text{NS},90), (\text{EW},30), (\text{EW},60), (\text{EW},90)\}$$

Thus:
- 4 Intersections $\implies 4 \times 6 = 24$ binary variables.
- 8 Intersections $\implies 8 \times 6 = 48$ binary variables.

---

## 3. The Exactly-One Constraint

An intersection can physically execute only **one** signal phase and green duration at any given time. Selecting 0 configurations leaves the junction unmanaged, while selecting multiple configurations causes physical collisions.

Mathematically, for each intersection $i$:
$$\sum_{k=1}^{6} x_{i, k} = 1$$

---

## 4. Penalty Term Expansion

To enforce $\sum_{k=1}^{6} x_{i, k} = 1$ in an unconstrained QUBO, we convert the equality constraint into a quadratic penalty term multiplied by penalty scalar $\lambda$:
$$\mathcal{P}_i = \lambda \left(1 - \sum_{k=1}^{6} x_{i, k}\right)^2$$

Expanding the quadratic expression:
$$\mathcal{P}_i = \lambda \left(1 - 2 \sum_{k=1}^6 x_{i, k} + \left(\sum_{k=1}^6 x_{i, k}\right)^2\right)$$
$$\mathcal{P}_i = \lambda \left(1 - 2 \sum_{k=1}^6 x_{i, k} + \sum_{k=1}^6 x_{i, k}^2 + 2 \sum_{1 \le k < m \le 6} x_{i, k} x_{i, m}\right)$$

Since $x_{i, k} \in \{0, 1\}$, we know $x_{i, k}^2 = x_{i, k}$. Substituting this property:
$$\mathcal{P}_i = \lambda + \sum_{k=1}^6 (-\lambda) x_{i, k} + \sum_{1 \le k < m \le 6} (2\lambda) x_{i, k} x_{i, m}$$

### QUBO Matrix Contributions:
- **Constant scalar offset**: $+\lambda$ per intersection.
- **Linear diagonal term $Q_{kk}$**: $-\lambda$ added to candidate traffic objective cost $H_{i, k}$.
- **Quadratic off-diagonal term $Q_{km}$** ($k \neq m$): $+2\lambda$ penalty between any two candidate selections at the same intersection.

---

## 5. How Queue Length Affects Cost

The traffic objective function minimizes unserved queues and waiting delays:
- **Green Direction**: Receives vehicle discharge rate $r_{\text{discharge}} = 1 \text{ veh/s}$. Remaining unserved queue after green time $d$:
  $$Q_{\text{rem}} = \max(0, Q_{\text{green}} - r_{\text{discharge}} \cdot d)$$
  Cost contribution: $w_{\text{queue}} \cdot Q_{\text{rem}}$

- **Red Direction**: Accumulates queue and vehicle delays over green duration $d$:
  Cost contribution: $w_{\text{wait}} \cdot Q_{\text{red}} \cdot \left(\frac{d}{30}\right) + w_{\text{congestion}} \cdot \text{Density}_{\text{red}} \cdot \left(\frac{d}{30}\right)$

Higher queue on NS penalizes keeping NS on RED and rewards granting NS a GREEN phase.

---

## 6. How Signal Duration Affects Cost

Duration $d \in \{30, 60, 90\}$ trades off queue clearance against red direction delay:
- Small queues ($Q_{\text{NS}} = 10$): $30\text{s}$ green clears the queue ($30 \times 1 = 30$ vehicles discharge capacity). Choosing $90\text{s}$ unnecessarily delays the EW direction for 60 additional seconds, increasing overall cost.
- Large queues ($Q_{\text{NS}} = 50$): $30\text{s}$ leaves 20 unserved vehicles. Choosing $90\text{s}$ clears all 50 vehicles, yielding a lower overall cost.

---

## 7. How Emergency Priority Affects Cost

When an emergency vehicle is detected on an approach direction:
- If configuration $(p, d)$ grants **GREEN** to the emergency direction:
  $$\text{Emergency Bonus} = - w_{\text{emergency}} \cdot \left(\frac{d}{30}\right)$$
- If configuration $(p, d)$ keeps emergency direction on **RED**:
  $$\text{Emergency Penalty} = + 2 \cdot w_{\text{emergency}} \cdot \left(\frac{d}{30}\right)$$

With $w_{\text{emergency}} = 500.0$, the penalty dominates standard traffic queue costs, forcing the optimizer to grant green to the emergency movement.

---

## 8. What the QUBO Minimizes

$$\min_{x \in \{0, 1\}^N} C(x) = \sum_{i, k} (H_{i, k} - \lambda) x_{i, k} + \sum_{i, k < m} 2\lambda x_{i, k} x_{i, m} + \sum_{(i,j), k, m} Q_{(i,k),(j,m)}^{\text{coupling}} x_{i, k} x_{j, m} + N \lambda$$

This minimizes the combined weighted sum of:
1. Total unserved traffic queue across all intersections.
2. Waiting delays on RED approaches.
3. Approach congestion ratios.
4. Emergency vehicle clearance delays.
5. Cross-intersection spillback penalties.

---

## 9. What the QUBO Does NOT Model Yet

1. Microscopic vehicle-by-vehicle acceleration and braking physics.
2. Pedestrian crossing countdown signals.
3. Continuous signal timing optimization (e.g. 43.5 seconds).
4. Full vehicle emissions and fuel consumption models (deferred until simulator provides telemetry).

---

## 10. Single Intersection Numerical Example

Consider Intersection `I1` with current traffic state:
- $\text{NS Queue} = 30$ vehicles (Density: 0.30)
- $\text{EW Queue} = 4$ vehicles (Density: 0.04)
- No emergency vehicles.
- Weights: $w_{\text{queue}} = 2.0, w_{\text{wait}} = 1.0, w_{\text{congestion}} = 5.0, \lambda = 1000.0$.

### Candidate Objective Costs $H_{I1, p, d}$:

1. **$(\text{NS}, 30)$**:
   - NS Discharge in 30s = $30 \times 1 = 30$. Remaining NS queue = $\max(0, 30 - 30) = 0$.
   - EW Red delay (4 vehicles waiting 30s): $w_{\text{wait}} \times 4 \times 1.0 = 4.0$.
   - EW Congestion: $w_{\text{congestion}} \times 0.04 \times 1.0 = 0.2$.
   - **Cost $H = 0 + 4.0 + 0.2 = 4.2$**

2. **$(\text{NS}, 60)$**:
   - Remaining NS queue = 0.
   - EW Red delay (4 vehicles waiting 60s): $1.0 \times 4 \times 2.0 = 8.0$.
   - EW Congestion: $5.0 \times 0.04 \times 2.0 = 0.4$.
   - **Cost $H = 0 + 8.0 + 0.4 = 8.4$**

3. **$(\text{EW}, 30)$**:
   - Remaining EW queue = 0.
   - NS Red delay (30 vehicles waiting 30s): $1.0 \times 30 \times 1.0 = 30.0$.
   - Remaining NS Queue penalty: $w_{\text{queue}} \times 30 = 60.0$.
   - NS Congestion: $5.0 \times 0.30 \times 1.0 = 1.5$.
   - **Cost $H = 0 + 30.0 + 60.0 + 1.5 = 91.5$**

### QUBO Decision:
$(\text{NS}, 30)$ achieves the minimal objective cost ($4.2$), correctly favoring the North-South phase with a 30s green duration!

---

## 11. QAOA Consumption Pipeline

In the upcoming QAOA phase, Qiskit will consume `QUBOProblem`:

```python
from qiskit_optimization.problems import QuadraticProgram
from qiskit_algorithms import QAOA

# 1. Convert QUBOProblem to Qiskit QuadraticProgram
qp = QuadraticProgram()
for var_name in qubo_problem.var_names:
    qp.binary_var(name=var_name)

qp.minimize(
    linear=qubo_problem.linear_coefficients,
    quadratic=qubo_problem.quadratic_coefficients,
    constant=qubo_problem.constant_offset
)

# 2. Convert QuadraticProgram to Ising Hamiltonian H_Problem
operator, offset = qp.to_ising()

# 3. Execute QAOA circuit on Quantum Sampler / Simulator
qaoa = QAOA(sampler=sampler, optimizer=cobyla)
result = qaoa.compute_minimum_eigenvalue(operator)

# 4. Decode optimal bitstring using TrafficQUBODecoder
decisions = TrafficQUBODecoder.decode(optimal_bitstring, qubo_problem)
```
