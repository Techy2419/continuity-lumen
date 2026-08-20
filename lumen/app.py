import os
import time
import threading
import uuid

import requests
from flask import Flask, request, jsonify, Response
from prometheus_client import generate_latest

import config
import metrics
import simulator
from state import state
from loki_client import push_log

app = Flask(__name__)


def _invoke_continuity_async(incident_name):
    """Fire-and-forget: ask Continuity to investigate, in the background.

    This is what makes Continuity genuinely event-driven rather than
    something a human has to remember to prompt -- it runs whether or
    not anyone has the dashboard open, e.g. via a plain curl trigger.
    """
    if not config.CONTINUITY_URL:
        return  # not configured (e.g. local dev without Continuity running)

    def _run():
        session_id = f"auto-{uuid.uuid4().hex[:10]}"
        base = config.CONTINUITY_URL.rstrip("/")
        try:
            requests.post(
                f"{base}/apps/{config.CONTINUITY_APP_NAME}/users/lumen-auto/sessions/{session_id}",
                json={},
                timeout=15,
            )
            requests.post(
                f"{base}/run",
                json={
                    "app_name": config.CONTINUITY_APP_NAME,
                    "user_id": "lumen-auto",
                    "session_id": session_id,
                    "new_message": {
                        "role": "user",
                        "parts": [{
                            "text": f"An incident was just detected ({incident_name}). "
                                    "Check Lumen's health and resolve any issues you find."
                        }],
                    },
                },
                timeout=120,
            )
        except Exception as e:
            push_log("control", "error", f"Autonomous Continuity invocation failed: {e}")

    threading.Thread(target=_run, daemon=True).start()


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# --- Per-service metrics endpoints, now reached by PATH instead of PORT ---

@app.route("/encoding/metrics")
def encoding_metrics():
    return Response(generate_latest(metrics.encoding_registry), mimetype="text/plain")


@app.route("/playback/metrics")
def playback_metrics():
    return Response(generate_latest(metrics.playback_registry), mimetype="text/plain")


@app.route("/ingest/metrics")
def ingest_metrics():
    return Response(generate_latest(metrics.ingest_registry), mimetype="text/plain")


@app.route("/recommendation/metrics")
def recommendation_metrics():
    return Response(generate_latest(metrics.recommendation_registry), mimetype="text/plain")


# --- Control API (incidents + remediation) -- same as before, unchanged behavior ---

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


# --- Trend tracking (direction, not just current value) ---
# Complements the rate tracking above: lets Continuity distinguish
# "recovering" (value dropping) from "stuck" (flat) from "getting worse"
# (still climbing) across consecutive triage checks, instead of only
# seeing a binary healthy/unhealthy snapshot each time.
_prev_values = {}


def _trend(key, current_value, flat_tolerance=0.05):
    """Returns (trend_label, per_second_rate_of_change)."""
    now = time.time()
    prev = _prev_values.get(key)
    _prev_values[key] = (current_value, now)
    if prev is None:
        return "unknown", 0.0
    prev_value, prev_time = prev
    dt = now - prev_time
    per_sec_rate = (current_value - prev_value) / dt if dt > 0 else 0.0
    if prev_value == 0:
        label = "stable" if current_value == 0 else "worsening"
    else:
        change_ratio = (current_value - prev_value) / max(abs(prev_value), 1)
        if change_ratio < -flat_tolerance:
            label = "recovering"
        elif change_ratio > flat_tolerance:
            label = "worsening"
        else:
            label = "stuck"
    return label, per_sec_rate
# Cumulative counters only ever go up, so comparing raw totals against a
# threshold makes "healthy" flicker forever after a single past incident,
# and is noisy from Lumen's normal small baseline error rate. Instead we
# track the previous reading's totals + timestamp and compute a real
# new-errors-per-second rate, the same way the dashboard does client-side.
_prev_counts = {}


def _error_rate(key, current_total):
    now = time.time()
    prev = _prev_counts.get(key)
    _prev_counts[key] = (current_total, now)
    if not prev:
        return 0.0
    prev_value, prev_time = prev
    dt = now - prev_time
    if dt <= 0:
        return 0.0
    return max(0.0, (current_total - prev_value) / dt)


@app.route("/status")
def status():
    return jsonify(state.snapshot())


@app.route("/dashboard/status")
def dashboard_status():
    s = state.snapshot()

    encoding_workers = _metric_value(metrics.encoding_registry, "encoding_worker_pool_size")
    encoding_queue = _metric_value(metrics.encoding_registry, "encoding_queue_depth")

    playback_5xx_total = _metric_value(
        metrics.playback_registry, "playback_requests_total_total", "status", "5xx"
    ) or _metric_value(metrics.playback_registry, "playback_requests_total", "status", "5xx")
    playback_2xx_total = _metric_value(
        metrics.playback_registry, "playback_requests_total_total", "status", "2xx"
    ) or _metric_value(metrics.playback_registry, "playback_requests_total", "status", "2xx")

    recommendation_5xx_total = _metric_value(
        metrics.recommendation_registry, "recommendation_requests_total_total", "status", "5xx"
    ) or _metric_value(
        metrics.recommendation_registry, "recommendation_requests_total", "status", "5xx"
    )

    ingest_queue = _metric_value(metrics.ingest_registry, "ingest_queue_depth")

    # Rate threshold set well above Lumen's normal baseline noise so a
    # random blip doesn't flip status; genuine incidents produce a rate
    # far higher than this.
    playback_rate = _error_rate("playback_5xx", playback_5xx_total)
    recommendation_rate = _error_rate("recommendation_5xx", recommendation_5xx_total)

    encoding_healthy = encoding_workers >= 10 and encoding_queue < 20
    playback_healthy = playback_rate < 1.0
    recommendation_healthy = recommendation_rate < 1.0

    # Trend: direction of change since the last time this endpoint was
    # called, so a caller can tell "actively recovering" apart from
    # "stuck" or "actively getting worse" instead of just a snapshot.
    encoding_queue_trend, encoding_queue_rate = _trend("encoding_queue", encoding_queue)
    playback_trend, _ = _trend("playback_rate", playback_rate)
    recommendation_trend, _ = _trend("recommendation_rate", recommendation_rate)

    # --- Media Impact: translate raw infrastructure health into the
    # consequence a studio crew or the audience would actually feel.
    # Deterministic arithmetic only -- no LLM guessing, no invented
    # confidence numbers. If it can't be computed from real data, it
    # isn't reported.
    media_impact = {
        "production": {
            "name": state.production_name,
            "workflow": state.production_workflow,
            "priority": state.production_priority,
        }
    }

    if state.incident_started_at is not None and encoding_queue > 0:
        elapsed_sec = time.time() - state.incident_started_at
        sla_sec = state.production_sla_minutes * 60
        remaining_sec = max(0, sla_sec - elapsed_sec)

        eta_sec = None
        if encoding_queue_rate < -0.01:  # genuinely draining
            eta_sec = encoding_queue / abs(encoding_queue_rate)

        if eta_sec is None:
            risk = "HIGH"
            reason = "queue not currently draining"
        elif eta_sec > remaining_sec:
            risk = "HIGH"
            reason = f"draining too slowly to clear before the {state.production_sla_minutes}min delivery window"
        elif eta_sec > remaining_sec * 0.5:
            risk = "MODERATE"
            reason = "draining, but delivery window is getting tight"
        else:
            risk = "LOW"
            reason = "draining fast enough to clear well within the delivery window"

        media_impact["production_risk"] = {
            "level": risk,
            "reason": reason,
            "assets_pending": round(encoding_queue),
            "delivery_window_remaining_sec": round(remaining_sec),
            "estimated_drain_time_sec": round(eta_sec) if eta_sec is not None else None,
        }
    else:
        media_impact["production_risk"] = {"level": "NONE", "assets_pending": 0}

    if not playback_healthy:
        media_impact["audience_impact"] = {
            "level": "HIGH",
            "reason": "viewers currently experiencing playback errors",
        }
    else:
        media_impact["audience_impact"] = {"level": "NONE"}

    return jsonify({
        "incidents": s,
        "media_impact": media_impact,
        "services": {
            "ingestion": {"healthy": True, "queue_depth": ingest_queue},
            "encoding": {
                "healthy": encoding_healthy,
                "worker_pool_size": encoding_workers,
                "queue_depth": encoding_queue,
                "queue_trend": encoding_queue_trend,
            },
            "playback": {
                "healthy": playback_healthy,
                "errors_5xx_new_per_sec": round(playback_rate, 3),
                "errors_5xx_lifetime": playback_5xx_total,
                "error_rate_trend": playback_trend,
            },
            "recommendation": {
                "healthy": recommendation_healthy,
                "errors_5xx_new_per_sec": round(recommendation_rate, 3),
                "errors_5xx_lifetime": recommendation_5xx_total,
                "error_rate_trend": recommendation_trend,
            },
        },
    })


@app.route("/incidents/trigger", methods=["POST"])
def trigger():
    name = request.json.get("name")
    with state.lock:
        if name == "encoding_crash":
            state.incident_encoding_crash = True
            if state.incident_started_at is None:
                state.incident_started_at = time.time()
        elif name == "latency_spike":
            state.incident_latency_spike = True
        elif name == "bad_deploy":
            state.incident_bad_deploy = True
        else:
            return jsonify({"error": "unknown incident", "valid": [
                "encoding_crash", "latency_spike", "bad_deploy"]}), 400
    push_log("control", "warn", f"Incident triggered: {name}")
    _invoke_continuity_async(name)
    return jsonify(state.snapshot())


@app.route("/incidents/clear", methods=["POST"])
def clear():
    with state.lock:
        state.incident_encoding_crash = False
        state.incident_latency_spike = False
        state.incident_bad_deploy = False
        state.incident_started_at = None
    push_log("control", "info", "All incidents cleared")
    return jsonify(state.snapshot())


@app.route("/remediate/scale_workers", methods=["POST"])
def scale_workers():
    n = int(request.json.get("n", 12))
    on_cooldown, wait = state.remediation_on_cooldown("scale_workers")
    if on_cooldown:
        return jsonify({
            "cooldown_active": True,
            "message": f"scale_workers was already run recently. "
                       f"Wait {wait}s before retrying -- if the triage "
                       f"snapshot still shows a problem, it likely needs "
                       f"more time to take effect, not a repeat action.",
            **state.snapshot(),
        }), 429
    with state.lock:
        state.worker_pool_target = n
        if n >= 10:
            state.incident_encoding_crash = False
            state.incident_started_at = None
    state.mark_remediated("scale_workers")
    push_log("control", "info", f"Agent scaled encoding workers to {n}")
    return jsonify(state.snapshot())


@app.route("/remediate/restart_service", methods=["POST"])
def restart_service():
    name = request.json.get("name")
    on_cooldown, wait = state.remediation_on_cooldown(f"restart_{name}")
    if on_cooldown:
        return jsonify({
            "cooldown_active": True,
            "message": f"restart_service('{name}') was already run recently. "
                       f"Wait {wait}s before retrying -- if the triage "
                       f"snapshot still shows a problem, it likely needs "
                       f"more time to take effect, not a repeat action.",
            **state.snapshot(),
        }), 429
    with state.lock:
        if name == "playback":
            state.incident_bad_deploy = False
            state.incident_latency_spike = False
    state.mark_remediated(f"restart_{name}")
    push_log("control", "info", f"Agent restarted service: {name}")
    return jsonify(state.snapshot())


@app.route("/remediate/rollback_deploy", methods=["POST"])
def rollback_deploy():
    service = request.json.get("service")
    on_cooldown, wait = state.remediation_on_cooldown(f"rollback_{service}")
    if on_cooldown:
        return jsonify({
            "cooldown_active": True,
            "message": f"rollback_deploy('{service}') was already run recently. "
                       f"Wait {wait}s before retrying -- if the triage "
                       f"snapshot still shows a problem, it likely needs "
                       f"more time to take effect, not a repeat action.",
            **state.snapshot(),
        }), 429
    with state.lock:
        state.incident_bad_deploy = False
    state.mark_remediated(f"rollback_{service}")
    push_log("control", "info", f"Agent rolled back deploy for: {service}")
    return jsonify(state.snapshot())


# Start the background traffic simulator once, when the app module loads
# (works both for local `python app.py` and for Cloud Run/gunicorn, since
# both import this module before serving requests).
simulator.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9100))
    app.run(host="0.0.0.0", port=port)
