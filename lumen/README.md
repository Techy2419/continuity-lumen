# Lumen — mock streaming backend for Continuity

Phase 1 scope only: the Encoding service + shared traffic simulator, wired
for metrics (Prometheus) + logs (Loki) into your existing Grafana Cloud
stack (`purplejeep46.grafana.net`). Playback/Ingest/Recommendation are
included too since the cascading-incident story needs them, but Encoding
is the one to verify first.

## 1. Install dependencies

    cd lumen
    pip install -r requirements.txt

## 2. Get your Grafana Cloud push credentials

You already have a service-account token for Grafana MCP — for Lumen you
need TWO SEPARATE credentials (metrics and logs use different endpoints):

- Grafana Cloud Portal -> your stack -> **Prometheus** card -> Details
  -> gives you the remote_write URL + your Prometheus instance ID
- Grafana Cloud Portal -> your stack -> **Loki** card -> Details
  -> gives you the Loki push URL + your Loki instance ID
- Cloud Portal -> **Access Policies** -> create a token with
  `metrics:write` and `logs:write` scopes (or reuse one with both)

## 3. Set Loki env vars and run Lumen

    set LOKI_URL=https://logs-prod-XXX.grafana.net
    set LOKI_USER=your_loki_instance_id
    set LOKI_TOKEN=your_access_policy_token

    python run_all.py

You should see the four metrics endpoints and the control API start up.
Without LOKI_URL set, logs just print to your terminal instead — fine for
local testing before you wire Grafana in.

## 4. Get metrics into Grafana Cloud (via Docker, since it's already working)

Copy `prometheus/prometheus.yml.template` to `prometheus/prometheus.yml`
and fill in the three REPLACE_WITH values from step 2. Then, since Docker
is already set up for Grafana MCP:

    docker run -d --name lumen-prometheus \
      -v "%cd%\prometheus\prometheus.yml:/etc/prometheus/prometheus.yml" \
      -p 9090:9090 \
      prom/prometheus --config.file=/etc/prometheus/prometheus.yml

`host.docker.internal` in the config is what lets the container reach
Lumen's services running directly on your machine (works out of the box
with Docker Desktop on Windows).

## 5. Verify data is arriving in Grafana

In Grafana Cloud, go to Explore, pick your Prometheus data source, and
query `encoding_worker_pool_size` — should show `12`. Pick your Loki data
source and query `{service="encoding"}` — should show log lines.

## 6. Trigger an incident

    curl -X POST http://localhost:9100/incidents/trigger -H "Content-Type: application/json" -d "{\"name\": \"encoding_crash\"}"

Watch `encoding_worker_pool_size` drop to 3 and `encoding_queue_depth`
climb in Grafana within ~15-30 seconds.

Clear it manually (without the agent) any time with:

    curl -X POST http://localhost:9100/incidents/clear

## Remediation endpoints (what Continuity's tools will call)

    POST /remediate/scale_workers      {"n": 12}
    POST /remediate/restart_service    {"name": "playback"}
    POST /remediate/rollback_deploy    {"service": "playback"}

Available incident names for /incidents/trigger:
`encoding_crash`, `latency_spike`, `bad_deploy`
