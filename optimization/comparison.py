import os
import sys
import json
import time
import subprocess

# ---------------------------------------------------------
# PROJECT PATH
# ---------------------------------------------------------

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------
# IMPORTS
# ---------------------------------------------------------

import traci

from simulation.metrics import (
    get_traffic_metrics,
    reset_metrics
)

from simulation.traffic import (
    get_traffic_density
)

from simulation.signals import (
    get_signal_states,
    set_signal_duration
)

from optimization.classical import (
    run_classical_optimizer
)

from optimization.qaoa import (
    run_quantum_optimizer
)


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

SUMO_BINARY = (
    r"C:\Program Files (x86)\Eclipse\Sumo\bin\sumo.exe"
)

SUMO_CONFIG = os.path.join(
    PROJECT_ROOT,
    "sumo",
    "simulation.sumocfg"
)

SIMULATION_STEPS = 600

RESULT_FILE = os.path.join(
    PROJECT_ROOT,
    "comparison_results.json"
)


# ---------------------------------------------------------
# SIGNAL CONTROL
# ---------------------------------------------------------

def apply_signal_plan(signal_plan):

    applied = {}


    for intersection, data in signal_plan.items():

        decision = data.get(
            "decision",
            0
        )


        if decision == 0:

            duration = 30

        else:

            duration = 60


        try:

            traci.trafficlight.setPhaseDuration(
                intersection,
                duration
            )

            applied[intersection] = {

                "decision": decision,

                "duration": duration,

                "success": True

            }

        except traci.TraCIException:

            applied[intersection] = {

                "decision": decision,

                "duration": duration,

                "success": False

            }


    return applied


# ---------------------------------------------------------
# TRAFFIC STATE
# ---------------------------------------------------------

def build_traffic_state(metrics):

    density = get_traffic_density()

    signals = get_signal_states()


    state = {

        "vehicle_count":
            metrics["vehicle_count"],

        "waiting_time":
            metrics["total_waiting_time"],

        "queue_lengths":
            metrics["queue_lengths"],

        "throughput":
            metrics["throughput"],

        "density":
            density,

        "signals":
            signals,

        "fuel_consumption":
            metrics["fuel_consumption"],

        "co2_emission":
            metrics["co2_emission"]

    }


    return state


# ---------------------------------------------------------
# START SUMO
# ---------------------------------------------------------

def start_sumo():

    if not os.path.exists(SUMO_BINARY):

        raise FileNotFoundError(
            f"SUMO executable not found:\n{SUMO_BINARY}"
        )


    if not os.path.exists(SUMO_CONFIG):

        raise FileNotFoundError(
            f"SUMO configuration not found:\n{SUMO_CONFIG}"
        )


    sumo_command = [

        SUMO_BINARY,

        "-c",
        SUMO_CONFIG,

        "--start",

        "--quit-on-end"

    ]


    subprocess.Popen(
        sumo_command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


    time.sleep(2)


    traci.start(
        [
            SUMO_BINARY,
            "-c",
            SUMO_CONFIG
        ]
    )


# ---------------------------------------------------------
# RUN ONE SIMULATION
# ---------------------------------------------------------

def run_simulation(mode):

    print()
    print("=" * 70)

    if mode == "classical":

        print("CLASSICAL FIXED-TIME BASELINE")

    else:

        print("QAOA ADAPTIVE CONTROL")

    print("=" * 70)


    reset_metrics()


    # -----------------------------------------------------
    # START SUMO
    # -----------------------------------------------------

    traci.start(
        [
            SUMO_BINARY,
            "-c",
            SUMO_CONFIG
        ]
    )


    # -----------------------------------------------------
    # METRIC ACCUMULATORS
    # -----------------------------------------------------

    total_waiting_time = 0

    total_queue = 0

    total_fuel = 0

    total_co2 = 0

    final_throughput = 0

    optimization_times = []

    last_bitstring = ""


    # -----------------------------------------------------
    # SIMULATION LOOP
    # -----------------------------------------------------

    for step in range(
        SIMULATION_STEPS
    ):

        traci.simulationStep()


        # -------------------------------------------------
        # GET METRICS ONCE
        # -------------------------------------------------

        metrics = get_traffic_metrics()


        total_waiting_time += (
            metrics["total_waiting_time"]
        )


        current_queue = sum(
            metrics["queue_lengths"].values()
        )


        total_queue += current_queue


        total_fuel += (
            metrics["fuel_consumption"]
        )


        total_co2 += (
            metrics["co2_emission"]
        )


        final_throughput = (
            metrics["throughput"]
        )


        # -------------------------------------------------
        # BUILD CURRENT TRAFFIC STATE
        # -------------------------------------------------

        traffic_state = build_traffic_state(
            metrics
        )


        # -------------------------------------------------
        # CLASSICAL CONTROL
        # -------------------------------------------------

        if mode == "classical":

            # Fixed-time baseline
            #
            # Every intersection receives
            # the same fixed duration.

            if step % 30 == 0:

                for intersection in [

                    "I1", "I2", "I3", "I4",

                    "I5", "I6", "I7", "I8"

                ]:

                    try:

                        set_signal_duration(
                            intersection,
                            30
                        )

                    except traci.TraCIException:

                        pass


        # -------------------------------------------------
        # QAOA CONTROL
        # -------------------------------------------------

        else:

            # Re-optimize periodically.

            if step % 20 == 0:

                start_time = time.time()


                result = run_quantum_optimizer(
                    traffic_state
                )


                optimization_time = (
                    time.time() - start_time
                )


                optimization_times.append(
                    optimization_time
                )


                last_bitstring = result.get(
                    "bitstring",
                    ""
                )


                apply_signal_plan(
                    result["signal_plan"]
                )


                print(
                    f"Step {step}: "
                    f"QAOA bitstring = "
                    f"{last_bitstring}"
                )


    # -----------------------------------------------------
    # CLOSE SIMULATION
    # -----------------------------------------------------

    traci.close()


    # -----------------------------------------------------
    # CALCULATE AVERAGES
    # -----------------------------------------------------

    average_waiting_time = (
        total_waiting_time /
        SIMULATION_STEPS
    )


    average_queue = (
        total_queue /
        SIMULATION_STEPS
    )


    average_fuel = (
        total_fuel /
        SIMULATION_STEPS
    )


    average_co2 = (
        total_co2 /
        SIMULATION_STEPS
    )


    # -----------------------------------------------------
    # FUEL / CO2 CONVERSION
    # -----------------------------------------------------

    # SUMO fuel consumption is mg/s.
    #
    # We report the average per simulation step
    # so that the two methods can be compared fairly.

    # CO2 is converted from mg/s to kg/s.

    average_co2_kg = (
        average_co2 / 1_000_000
    )


    # Approximate gasoline-equivalent density:
    # 745,000 mg per litre.

    average_fuel_litres = (
        average_fuel / 745_000
    )


    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    result = {

        "mode": mode,

        "simulation_steps":
            SIMULATION_STEPS,

        "average_waiting_time":
            average_waiting_time,

        "average_queue":
            average_queue,

        "throughput":
            final_throughput,

        "average_fuel_litres":
            average_fuel_litres,

        "average_co2_kg":
            average_co2_kg,

        "average_fuel_raw":
            average_fuel,

        "average_co2_raw":
            average_co2,

        "optimization_runs":
            len(optimization_times),

        "average_optimization_time":
            (
                sum(optimization_times) /
                len(optimization_times)
                if optimization_times
                else 0
            ),

        "last_bitstring":
            last_bitstring

    }


    return result


# ---------------------------------------------------------
# PERCENTAGE CHANGE
# ---------------------------------------------------------

def calculate_change(
    classical,
    quantum
):

    if classical == 0:

        return 0

    return (
        (quantum - classical)
        / classical
    ) * 100


# ---------------------------------------------------------
# MAIN COMPARISON
# ---------------------------------------------------------

def main():

    print()
    print("Starting comparison...")
    print()


    # -----------------------------------------------------
    # CLASSICAL
    # -----------------------------------------------------

    classical_result = run_simulation(
        "classical"
    )


    # -----------------------------------------------------
    # QAOA
    # -----------------------------------------------------

    quantum_result = run_simulation(
        "quantum"
    )


    # -----------------------------------------------------
    # CHANGES
    # -----------------------------------------------------

    waiting_change = calculate_change(
        classical_result[
            "average_waiting_time"
        ],
        quantum_result[
            "average_waiting_time"
        ]
    )


    queue_change = calculate_change(
        classical_result[
            "average_queue"
        ],
        quantum_result[
            "average_queue"
        ]
    )


    throughput_change = calculate_change(
        classical_result[
            "throughput"
        ],
        quantum_result[
            "throughput"
        ]
    )


    fuel_change = calculate_change(
        classical_result[
            "average_fuel_litres"
        ],
        quantum_result[
            "average_fuel_litres"
        ]
    )


    co2_change = calculate_change(
        classical_result[
            "average_co2_kg"
        ],
        quantum_result[
            "average_co2_kg"
        ]
    )


    # -----------------------------------------------------
    # COMPARISON OBJECT
    # -----------------------------------------------------

    comparison = {

        "classical": classical_result,

        "qaoa": quantum_result,

        "change_percent": {

            "waiting_time":
                waiting_change,

            "queue":
                queue_change,

            "throughput":
                throughput_change,

            "fuel":
                fuel_change,

            "co2":
                co2_change

        }

    }


    # -----------------------------------------------------
    # SAVE JSON
    # -----------------------------------------------------

    with open(
        RESULT_FILE,
        "w"
    ) as file:

        json.dump(
            comparison,
            file,
            indent=4
        )


    # -----------------------------------------------------
    # PRINT RESULTS
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("CLASSICAL VS QAOA COMPARISON")
    print("=" * 70)


    print()

    print(
        f"{'Metric':<25}"
        f"{'Classical':>15}"
        f"{'QAOA':>15}"
        f"{'Change %':>15}"
    )

    print("-" * 70)


    print(
        f"{'Average Waiting Time':<25}"
        f"{classical_result['average_waiting_time']:>15.2f}"
        f"{quantum_result['average_waiting_time']:>15.2f}"
        f"{waiting_change:>14.2f}%"
    )


    print(
        f"{'Average Queue':<25}"
        f"{classical_result['average_queue']:>15.2f}"
        f"{quantum_result['average_queue']:>15.2f}"
        f"{queue_change:>14.2f}%"
    )


    print(
        f"{'Throughput':<25}"
        f"{classical_result['throughput']:>15}"
        f"{quantum_result['throughput']:>15}"
        f"{throughput_change:>14.2f}%"
    )


    print(
        f"{'Fuel (L/step)':<25}"
        f"{classical_result['average_fuel_litres']:>15.4f}"
        f"{quantum_result['average_fuel_litres']:>15.4f}"
        f"{fuel_change:>14.2f}%"
    )


    print(
        f"{'CO2 (kg/step)':<25}"
        f"{classical_result['average_co2_kg']:>15.4f}"
        f"{quantum_result['average_co2_kg']:>15.4f}"
        f"{co2_change:>14.2f}%"
    )


    print("-" * 70)


    print()
    print(
        "QAOA optimization runs:",
        quantum_result["optimization_runs"]
    )


    print(
        "Average QAOA optimization time:",
        f"{quantum_result['average_optimization_time']:.4f}",
        "seconds"
    )


    print(
        "Last QAOA bitstring:",
        quantum_result["last_bitstring"]
    )


    print()
    print(
        "Results saved to:"
    )

    print(
        RESULT_FILE
    )


    print()
    print("=" * 70)
    print("COMPARISON COMPLETE")
    print("=" * 70)


# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------

if __name__ == "__main__":

    main()
