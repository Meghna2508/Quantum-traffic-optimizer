from metrics import get_traffic_metrics
from traffic import get_traffic_density
from signals import get_signal_states


def get_traffic_state():

    metrics = get_traffic_metrics()
    density = get_traffic_density()
    signals = get_signal_states()

    state = {
        "vehicle_count": metrics["vehicle_count"],
        "waiting_time": metrics["total_waiting_time"],
        "queue_lengths": metrics["queue_lengths"],
        "density": density,
        "signals": signals
    }

    return state