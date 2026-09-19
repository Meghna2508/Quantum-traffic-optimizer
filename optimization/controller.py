@'
from simulation.signals import set_signal_phase, set_signal_duration

def apply_signal_plan(signal_plan):

    results = {}

    for intersection, data in signal_plan.items():

        decision = data.get("decision", 0)

        # 0 = first green direction
        # 1 = second green direction
        phase = 0 if decision == 0 else 2

        duration = 30 if decision == 0 else 60

        phase_success = set_signal_phase(
            intersection,
            phase
        )

        duration_success = set_signal_duration(
            intersection,
            duration
        )

        results[intersection] = {
            "success": phase_success and duration_success,
            "decision": decision,
            "phase": phase,
            "duration": duration
        }

    return results
'@ | Set-Content optimization\controller.py