import os

# --- Grafana Cloud Loki (logs) push settings ---
# Find these in Grafana Cloud Portal -> your stack -> Loki card -> Details
LOKI_URL = os.environ.get("LOKI_URL", "")        # e.g. https://logs-prod-006.grafana.net
LOKI_USER = os.environ.get("LOKI_USER", "")      # your Loki instance ID (a number)
LOKI_TOKEN = os.environ.get("LOKI_TOKEN", "")    # a Cloud Access Policy token with logs:write

# --- Local ports for each mock service ---
ENCODING_PORT = int(os.environ.get("ENCODING_PORT", 9101))
PLAYBACK_PORT = int(os.environ.get("PLAYBACK_PORT", 9102))
INGEST_PORT = int(os.environ.get("INGEST_PORT", 9103))
RECOMMENDATION_PORT = int(os.environ.get("RECOMMENDATION_PORT", 9104))
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", 9100))
