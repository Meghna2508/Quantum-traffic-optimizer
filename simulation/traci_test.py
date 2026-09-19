import traci
from metrics import get_traffic_metrics
from signals import get_signal_states
from traffic import get_traffic_density

traci.start([
    "sumo",
    "-c", "sumo/simulation.sumocfg"
])

for step in range(100):
    traci.simulationStep()

    metrics = get_traffic_metrics()
    signals = get_signal_states()
    density = get_traffic_density()

    print(f"\nStep: {step}")
    print(f"Vehicles: {metrics['vehicle_count']}")
    print(f"Waiting Time: {metrics['total_waiting_time']:.2f}s")

    print("Queue Lengths:")
    for intersection, queue in metrics["queue_lengths"].items():
        print(f"  {intersection}: {queue}")

    print("Signals:")
    for intersection, state in signals.items():
        print(f"  {intersection}: {state}")

    print("Traffic Density:")
    for intersection, value in density.items():
        print(f"  {intersection}: {value:.2f}")

traci.close()