from flask import Flask, request, jsonify

from state import state
from loki_client import push_log
import config
import metrics

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _metric_value(registry, name, label_key=None, label_value=None, default=0):
    for metric_family in registry.collect():
        for sample in metric_family.samples:
            if sample.name != name:
                continue
            if label_key is not None:
                if sample.labels.get(label_key) != label_value:
                    continue
            return sample.value
    return default


@app.route("/status")
def status():
    return jsonify(state.snapshot())


@app.route("/dashboard/status")
def dashboard_status():
    """Rich JSON snapshot for the frontend dashboard cards."""
    s = state.snapshot()

    encoding_workers = _metric_value(metrics.encoding_registry, "encoding_worker_pool_size")
    encoding_queue = _metric_value(metrics.encoding_registry, "encoding_queue_depth")

    playback_5xx = _metric_value(
        metrics.playback_registry, "playback_requests_total_total", "status", "5xx"
    ) or _metric_value(metrics.playback_registry, "playback_requests_total", "status", "5xx")
    playback_2xx = _metric_value(
        metrics.playback_registry, "playback_requests_total_total", "status", "2xx"
    ) or _metric_value(metrics.playback_registry, "playback_requests_total", "status", "2xx")

    recommendation_5xx = _metric_value(
        metrics.recommendation_registry, "recommendation_requests_total_total", "status", "5xx"
    ) or _metric_value(
        metrics.recommendation_registry, "recommendation_requests_total", "status", "5xx"
    )

    ingest_queue = _metric_value(metrics.ingest_registry, "ingest_queue_depth")

    encoding_healthy = encoding_workers >= 10 and encoding_queue < 20
    playback_healthy = playback_5xx < 5 or (playback_2xx > 0 and playback_5xx / max(playback_2xx, 1) < 0.05)

    return jsonify({
        "incidents": s,
        "services": {
            "ingestion": {
                "healthy": True,
                "queue_depth": ingest_queue,
            },
            "encoding": {
                "healthy": encoding_healthy,
                "worker_pool_size": encoding_workers,
                "queue_depth": encoding_queue,
            },
            "playback": {
                "healthy": playback_healthy,
                "errors_5xx_total": playback_5xx,
                "requests_2xx_total": playback_2xx,
            },
            "recommendation": {
                "healthy": recommendation_5xx < 5,
                "errors_5xx_total": recommendation_5xx,
            },
        },
    })


# --- Incident controls (you use these to script the demo) ---

@app.route("/incidents/trigger", methods=["POST"])
def trigger():
    name = request.json.get("name")
    with state.lock:
        if name == "encoding_crash":
            state.incident_encoding_crash = True
        elif name == "latency_spike":
            state.incident_latency_spike = True
        elif name == "bad_deploy":
            state.incident_bad_deploy = True
        else:
            return jsonify({"error": "unknown incident", "valid": [
                "encoding_crash", "latency_spike", "bad_deploy"]}), 400
    push_log("control", "warn", f"Incident triggered: {name}")
    return jsonify(state.snapshot())


@app.route("/incidents/clear", methods=["POST"])
def clear():
    with state.lock:
        state.incident_encoding_crash = False
        state.incident_latency_spike = False
        state.incident_bad_deploy = False
    push_log("control", "info", "All incidents cleared")
    return jsonify(state.snapshot())


# --- Remediation tools: these are what the Continuity agent calls ---

@app.route("/remediate/scale_workers", methods=["POST"])
def scale_workers():
    n = int(request.json.get("n", 12))
    with state.lock:
        state.worker_pool_target = n
        if n >= 10:
            state.incident_encoding_crash = False
    push_log("control", "info", f"Agent scaled encoding workers to {n}")
    return jsonify(state.snapshot())


@app.route("/remediate/restart_service", methods=["POST"])
def restart_service():
    name = request.json.get("name")
    with state.lock:
        if name == "playback":
            state.incident_bad_deploy = False
            state.incident_latency_spike = False
    push_log("control", "info", f"Agent restarted service: {name}")
    return jsonify(state.snapshot())


@app.route("/remediate/rollback_deploy", methods=["POST"])
def rollback_deploy():
    service = request.json.get("service")
    with state.lock:
        state.incident_bad_deploy = False
    push_log("control", "info", f"Agent rolled back deploy for: {service}")
    return jsonify(state.snapshot())


def run():
    app.run(host="0.0.0.0", port=config.CONTROL_PORT)
