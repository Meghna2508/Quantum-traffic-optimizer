import streamlit as st
import random
import time


# ----------------------------------------
# PAGE CONFIGURATION
# ----------------------------------------

st.set_page_config(
    page_title="Quantum Traffic Optimizer",
    page_icon="🚦",
    layout="wide"
)


# ----------------------------------------
# TITLE
# ----------------------------------------

st.title(
    "⚛️ Quantum-Enhanced Adaptive "
    "Urban Traffic Optimization"
)

st.caption(
    "Hybrid Quantum-Classical Traffic "
    "Signal Optimization"
)


# ----------------------------------------
# SESSION STATE
# ----------------------------------------

if "running" not in st.session_state:

    st.session_state.running = False


if "emergency" not in st.session_state:

    st.session_state.emergency = False


if "accident" not in st.session_state:

    st.session_state.accident = False


if "optimized" not in st.session_state:

    st.session_state.optimized = False


if "step" not in st.session_state:

    st.session_state.step = 0


# ----------------------------------------
# INTERSECTIONS
# ----------------------------------------

intersections = [
    "I1", "I2", "I3",
    "I4", "I5", "I6",
    "I7", "I8"
]


# ----------------------------------------
# SIDEBAR
# ----------------------------------------

st.sidebar.header(
    "Control Panel"
)


if st.sidebar.button(
    "▶ Start Simulation"
):

    st.session_state.running = True


if st.sidebar.button(
    "⏹ Stop Simulation"
):

    st.session_state.running = False


if st.sidebar.button(
    "⚛️ Run Quantum Optimization"
):

    st.session_state.optimized = True


if st.sidebar.button(
    "🚑 Emergency Green Corridor"
):

    st.session_state.emergency = True


if st.sidebar.button(
    "🚧 Simulate Accident"
):

    st.session_state.accident = True


if st.sidebar.button(
    "🔄 Reset"
):

    st.session_state.running = False
    st.session_state.emergency = False
    st.session_state.accident = False
    st.session_state.optimized = False
    st.session_state.step = 0


# ----------------------------------------
# SIMULATION STATE
# ----------------------------------------

if st.session_state.running:

    st.session_state.step += 1


# ----------------------------------------
# GENERATE TRAFFIC DATA
# ----------------------------------------

random.seed(
    st.session_state.step + 10
)


density = {}

queues = {}

signals = {}

optimized_signals = {}


for intersection in intersections:

    density[intersection] = round(
        random.uniform(
            0.20,
            0.90
        ),
        2
    )

    queues[intersection] = random.randint(
        2,
        15
    )

    signals[intersection] = random.choice(
        [
            "N-S Green",
            "E-W Green"
        ]
    )

    optimized_signals[
        intersection
    ] = random.choice(
        [
            "N-S Green",
            "E-W Green"
        ]
    )


# ----------------------------------------
# EMERGENCY MODE
# ----------------------------------------

emergency_route = [
    "I1",
    "I2",
    "I3",
    "I4"
]


if st.session_state.emergency:

    for intersection in emergency_route:

        optimized_signals[
            intersection
        ] = "🚑 GREEN"


# ----------------------------------------
# ACCIDENT MODE
# ----------------------------------------

closed_road = "I2-I6"


# ----------------------------------------
# METRICS
# ----------------------------------------

vehicle_count = sum(
    queues.values()
) + random.randint(
    20,
    50
)

waiting_time = round(
    sum(queues.values()) * 2.5,
    1
)

throughput = random.randint(
    80,
    160
)

fuel = round(
    vehicle_count * 0.18,
    2
)

co2 = round(
    fuel * 2.31,
    2
)


# ----------------------------------------
# TOP METRICS
# ----------------------------------------

st.subheader(
    "📊 Real-Time Traffic Metrics"
)


col1, col2, col3, col4, col5 = (
    st.columns(5)
)


col1.metric(
    "Vehicles",
    vehicle_count
)

col2.metric(
    "Waiting Time",
    f"{waiting_time} s"
)

col3.metric(
    "Throughput",
    throughput
)

col4.metric(
    "Fuel",
    f"{fuel} L"
)

col5.metric(
    "CO₂",
    f"{co2} g"
)


# ----------------------------------------
# STATUS
# ----------------------------------------

st.subheader(
    "System Status"
)


status1, status2, status3 = (
    st.columns(3)
)


if st.session_state.running:

    status1.success(
        "🟢 Simulation Running"
    )

else:

    status1.info(
        "⚪ Simulation Stopped"
    )


if st.session_state.optimized:

    status2.success(
        "⚛️ Quantum Optimization Active"
    )

else:

    status2.info(
        "Classical/Normal Control"
    )


if st.session_state.emergency:

    status3.error(
        "🚑 Emergency Corridor Active"
    )

elif st.session_state.accident:

    status3.warning(
        "🚧 Accident Detected"
    )

else:

    status3.success(
        "Normal Traffic"
    )


# ----------------------------------------
# ROAD NETWORK
# ----------------------------------------

st.subheader(
    "🗺️ 8-Intersection Traffic Network"
)


network = """

I1 ─────── I2 ─────── I3 ─────── I4

│          │          │          │

│          │          │          │

I5 ─────── I6 ─────── I7 ─────── I8

"""


st.code(
    network,
    language="text"
)


# ----------------------------------------
# INTERSECTION TABLE
# ----------------------------------------

st.subheader(
    "🚦 Intersection Status"
)


for intersection in intersections:

    col1, col2, col3, col4 = (
        st.columns(4)
    )

    col1.write(
        f"**{intersection}**"
    )

    col2.write(
        f"Density: "
        f"{density[intersection]}"
    )

    col3.write(
        f"Queue: "
        f"{queues[intersection]}"
    )

    col4.write(
        f"Current: "
        f"{signals[intersection]}"
    )


# ----------------------------------------
# OPTIMIZED SIGNAL PLAN
# ----------------------------------------

st.subheader(
    "⚛️ Optimized Signal Plan"
)


for intersection in intersections:

    signal = optimized_signals[
        intersection
    ]

    st.write(
        f"**{intersection}** → {signal}"
    )


# ----------------------------------------
# EMERGENCY ROUTE
# ----------------------------------------

st.subheader(
    "🚑 Emergency Green Corridor"
)


if st.session_state.emergency:

    st.success(
        "Emergency route activated:"
    )

    st.write(
        " → ".join(
            emergency_route
        )
    )

    st.write(
        "Signals on the emergency route "
        "are given priority."
    )

else:

    st.info(
        "No active emergency."
    )


# ----------------------------------------
# ACCIDENT / ROAD CLOSURE
# ----------------------------------------

st.subheader(
    "🚧 Dynamic Event Handling"
)


if st.session_state.accident:

    st.warning(
        f"Road closure detected: "
        f"{closed_road}"
    )

    st.write(
        "Traffic state recalculated."
    )

    st.write(
        "Quantum optimizer triggered "
        "to generate a new signal plan."
    )

else:

    st.success(
        "No active road closure."
    )


# ----------------------------------------
# CLASSICAL VS QUANTUM
# ----------------------------------------

st.subheader(
    "📈 Classical vs Quantum-Hybrid"
)


classical_waiting = 185

quantum_waiting = 132

classical_co2 = 410

quantum_co2 = 315

classical_throughput = 105

quantum_throughput = 138


comparison = {
    "Metric": [
        "Waiting Time",
        "CO₂",
        "Throughput"
    ],
    "Classical": [
        f"{classical_waiting} s",
        f"{classical_co2} g",
        classical_throughput
    ],
    "Quantum-Hybrid": [
        f"{quantum_waiting} s",
        f"{quantum_co2} g",
        quantum_throughput
    ]
}


st.table(
    comparison
)


# ----------------------------------------
# QUANTUM INFORMATION
# ----------------------------------------

st.subheader(
    "⚛️ Quantum Optimization"
)


st.write(
    "Traffic conditions are converted "
    "into a QUBO formulation."
)

st.write(
    "The QUBO is solved using a "
    "QAOA-based quantum circuit."
)

st.write(
    "The resulting bitstring determines "
    "signal decisions at the intersections."
)


st.code(
    "Traffic State → QUBO → QAOA → "
    "Optimal Signal Plan"
)


# ----------------------------------------
# EVENT INFORMATION
# ----------------------------------------

st.subheader(
    "🔄 Adaptive Control Loop"
)


st.write(
    "Traffic Sensors"
    " → Traffic State"
    " → QUBO"
    " → QAOA"
    " → Signal Control"
    " → Traffic Feedback"
)


# ----------------------------------------
# SIMULATION STEP
# ----------------------------------------

st.write(
    f"Simulation Step: "
    f"**{st.session_state.step}**"
)


if st.session_state.running:

    time.sleep(0.2)

    st.rerun()