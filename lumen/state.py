import threading


class LumenState:
    """Shared, thread-safe state for the whole Lumen mock backend.

    This is what incidents flip and what remediation tools (called by the
    Continuity agent) reset back to normal.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.worker_pool_target = 12
        self.incident_encoding_crash = False
        self.incident_latency_spike = False
        self.incident_bad_deploy = False
        self.last_remediation = {}  # action_key -> timestamp

    def remediation_on_cooldown(self, action_key, cooldown_seconds=90):
        import time
        last = self.last_remediation.get(action_key)
        if last is None:
            return False, 0
        elapsed = time.time() - last
        if elapsed < cooldown_seconds:
            return True, round(cooldown_seconds - elapsed)
        return False, 0

    def mark_remediated(self, action_key):
        import time
        self.last_remediation[action_key] = time.time()

    def snapshot(self):
        with self.lock:
            return {
                "worker_pool_target": self.worker_pool_target,
                "incident_encoding_crash": self.incident_encoding_crash,
                "incident_latency_spike": self.incident_latency_spike,
                "incident_bad_deploy": self.incident_bad_deploy,
            }


state = LumenState()
