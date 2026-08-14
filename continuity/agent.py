import requests

from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams


grafana = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="http://localhost:8000/mcp",
    )
)

LUMEN_CONTROL_URL = "http://localhost:9100"


def get_lumen_triage_snapshot() -> dict:
    """Get an instant, complete health snapshot of all Lumen services.

    ALWAYS call this FIRST, before any Grafana queries. It returns current
    worker counts, queue depths, and error rates for every service in a
    single call, with no Grafana round-trip needed. Only fall back to
    Grafana MCP tools (query_loki_logs, query_prometheus, etc.) for a
    SPECIFIC service this snapshot flags as unhealthy, to see root-cause
    log detail Grafana has that this snapshot doesn't.

    Returns:
        A dict with per-service health status and key metrics.
    """
    resp = requests.get(f"{LUMEN_CONTROL_URL}/dashboard/status", timeout=5)
    return resp.json()


def scale_encoding_workers(n: int) -> dict:
    """Scale Lumen's encoding worker pool to n workers.

    Use this when Grafana metrics/logs show the encoding worker pool has
    dropped below its healthy target (normally 12) and the queue is
    backing up as a result.

    Args:
        n: target number of encoding workers (normal healthy value is 12)

    Returns:
        The resulting Lumen system state after scaling.
    """
    resp = requests.post(f"{LUMEN_CONTROL_URL}/remediate/scale_workers",
                          json={"n": n}, timeout=5)
    return resp.json()


def restart_service(name: str) -> dict:
    """Restart a Lumen service to clear a stuck/degraded state.

    Use this for issues that aren't a worker-capacity problem -- e.g. a
    latency spike or elevated error rate on the playback service that
    doesn't trace back to encoding backlog.

    Args:
        name: the service to restart, e.g. "playback"

    Returns:
        The resulting Lumen system state after the restart.
    """
    resp = requests.post(f"{LUMEN_CONTROL_URL}/remediate/restart_service",
                          json={"name": name}, timeout=5)
    return resp.json()


def rollback_deploy(service: str) -> dict:
    """Roll back a recent bad deployment on a Lumen service.

    Use this when logs/metrics indicate a new deployment introduced an
    elevated error rate on a service.

    Args:
        service: the service to roll back, e.g. "playback"

    Returns:
        The resulting Lumen system state after the rollback.
    """
    resp = requests.post(f"{LUMEN_CONTROL_URL}/remediate/rollback_deploy",
                          json={"service": service}, timeout=5)
    return resp.json()


root_agent = Agent(
    model="gemini-3.5-flash",
    name="continuity",
    description=(
        "Continuity is an autonomous reliability and incident-response "
        "agent for Lumen, a mock media and entertainment platform."
    ),
    instruction="""
You are Continuity, an autonomous reliability and incident-response agent
responsible for Lumen's production systems.

Your mission is to detect, investigate, diagnose, remediate, verify, and report
incidents affecting Lumen.

Lumen contains these services:

- Video Ingestion
- Video Encoding
- Playback API
- Recommendation Service

Your known Grafana datasource UIDs (do NOT waste calls discovering these
with list_datasources -- they never change):
- Prometheus: grafanacloud-prom
- Loki: grafanacloud-logs

Follow this operational cycle:

1. DETECT
   ALWAYS start by calling get_lumen_triage_snapshot(). This one call
   tells you which services are healthy and which aren't, with their key
   metrics, instantly. Do NOT begin with Grafana discovery calls
   (list_datasources, list_prometheus_metric_names, list_prometheus_label_*,
   list_loki_label_*) -- you already know the datasource UIDs above, and
   the triage snapshot already tells you what's abnormal.

2. INVESTIGATE
   Only for services the triage snapshot flagged as unhealthy: query
   Grafana logs (query_loki_logs with the known datasourceUid) for that
   SPECIFIC service to find root-cause detail the snapshot doesn't have
   (error messages, crash reasons). One or two log queries per unhealthy
   service is enough. Do not query healthy services. Do not query
   unrelated datasources like grafanacloud-usage or grafanacloud-ml-metrics.

3. DIAGNOSE
   Determine the most likely root cause using evidence from the triage
   snapshot and your log queries. Never invent evidence or claim certainty
   without supporting data.

4. REMEDIATE
   Only execute remediation actions when an authorized remediation tool is
   available and the evidence supports the action. Your available
   remediation tools are: scale_encoding_workers, restart_service, and
   rollback_deploy. Use scale_encoding_workers when the encoding worker
   pool has dropped below its healthy level (12). Use restart_service for
   a degraded service that isn't a worker-capacity issue. Use
   rollback_deploy when logs indicate a recent bad deployment.

5. VERIFY
   Call get_lumen_triage_snapshot() again to confirm recovery. This is
   enough -- you do not need additional Grafana queries to verify unless
   the triage snapshot still shows a problem.

6. REPORT
   Clearly summarize:
   - What happened
   - Which service was affected
   - Evidence discovered
   - Root cause
   - Remediation performed
   - Verification result

Important rules:

- NEVER call a tool with the exact same name and arguments more than once
  in a single investigation. If you already have the result, use it --
  do not re-query it "to be sure."
- Be efficient: a typical investigation should take 3-8 tool calls total,
  not 20+. Triage snapshot, 1-2 targeted log queries per unhealthy
  service, the remediation call, and a final verification snapshot is
  usually the whole loop.
- Prefer Grafana data over assumptions.
- Do not claim that an incident exists without evidence.
- Do not claim that a remediation succeeded until verification confirms it.
- Do not perform destructive or unauthorized actions.
- When investigating an incident, correlate metrics and logs whenever
  possible.
- Be concise but provide enough technical evidence for an engineer to trust
  your conclusion.
""",
    tools=[grafana, get_lumen_triage_snapshot, scale_encoding_workers, restart_service, rollback_deploy],
)
