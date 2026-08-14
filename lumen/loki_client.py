import time
import requests

import config


def push_log(service, level, message, labels=None):
    """Push a single log line to Grafana Cloud Loki.

    Falls back to printing locally if LOKI_URL isn't configured yet, so you
    can develop Lumen before you've set up Grafana Cloud credentials.
    """
    if not config.LOKI_URL:
        print(f"[{service}] {level}: {message}")
        return

    stream_labels = {"service": service, "level": level}
    if labels:
        stream_labels.update(labels)

    ts_ns = str(int(time.time() * 1e9))
    payload = {"streams": [{"stream": stream_labels, "values": [[ts_ns, message]]}]}

    try:
        resp = requests.post(
            f"{config.LOKI_URL.rstrip('/')}/loki/api/v1/push",
            json=payload,
            auth=(config.LOKI_USER, config.LOKI_TOKEN) if config.LOKI_USER else None,
            timeout=5,
        )
        if resp.status_code >= 300:
            print(f"Loki push rejected: HTTP {resp.status_code} - {resp.text[:300]}")
    except Exception as e:
        print(f"Loki push failed: {e}")
