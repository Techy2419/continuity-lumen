import random
import threading
import time

from state import state
from loki_client import push_log
import metrics


def _loop():
    queue = 0
    while True:
        s = state.snapshot()

        # --- Encoding ---
        worker_pool = 3 if s["incident_encoding_crash"] else s["worker_pool_target"]
        metrics.encoding_worker_pool_size.set(worker_pool)

        incoming_jobs = random.randint(8, 15)
        capacity = worker_pool * 2
        queue = max(0, queue + incoming_jobs - capacity)
        metrics.encoding_queue_depth.set(queue)

        if queue > 20:
            metrics.encoding_jobs_failed_total.inc(random.randint(1, 3))
            push_log(
                "encoding", "error",
                f"encoding backlog critical: queue_depth={queue} worker_pool={worker_pool}",
            )
        else:
            metrics.encoding_jobs_completed_total.inc(incoming_jobs)

        # --- Playback (cascades from encoding backlog + its own incidents) ---
        error_chance = 0.02
        if queue > 20:
            error_chance += 0.25
        if s["incident_latency_spike"]:
            error_chance += 0.1
        if s["incident_bad_deploy"]:
            error_chance += 0.35

        for _ in range(random.randint(20, 40)):
            if random.random() < error_chance:
                metrics.playback_requests_total.labels(status="5xx").inc()
                if random.random() < 0.1:
                    push_log(
                        "playback", "error",
                        f"playback request failed: 5xx "
                        f"(queue_depth={queue}, bad_deploy={s['incident_bad_deploy']})",
                    )
            else:
                metrics.playback_requests_total.labels(status="2xx").inc()
            latency = 0.05 + (0.5 if s["incident_latency_spike"] else 0) + random.random() * 0.05
            metrics.playback_latency_seconds.observe(latency)

        # --- Recommendation (depends on playback health) ---
        for _ in range(random.randint(10, 20)):
            if random.random() < error_chance * 0.7:
                metrics.recommendation_requests_total.labels(status="5xx").inc()
            else:
                metrics.recommendation_requests_total.labels(status="2xx").inc()
            metrics.recommendation_latency_seconds.observe(0.03 + random.random() * 0.03)

        # --- Ingest (steady, not tied to incidents) ---
        metrics.ingest_uploads_total.inc(random.randint(1, 5))
        metrics.ingest_queue_depth.set(random.randint(0, 5))

        time.sleep(2)


def start():
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
