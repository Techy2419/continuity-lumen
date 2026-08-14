from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# Each service gets its own registry so its /metrics endpoint only shows
# metrics relevant to that service (mirrors how real microservices work).

encoding_registry = CollectorRegistry()
encoding_worker_pool_size = Gauge(
    "encoding_worker_pool_size", "Number of active encoding workers", registry=encoding_registry
)
encoding_queue_depth = Gauge(
    "encoding_queue_depth", "Jobs waiting to be encoded", registry=encoding_registry
)
encoding_jobs_completed_total = Counter(
    "encoding_jobs_completed_total", "Total encoding jobs completed", registry=encoding_registry
)
encoding_jobs_failed_total = Counter(
    "encoding_jobs_failed_total", "Total encoding jobs failed", registry=encoding_registry
)

playback_registry = CollectorRegistry()
playback_requests_total = Counter(
    "playback_requests_total", "Total playback requests", ["status"], registry=playback_registry
)
playback_latency_seconds = Histogram(
    "playback_latency_seconds", "Playback request latency", registry=playback_registry
)

ingest_registry = CollectorRegistry()
ingest_uploads_total = Counter(
    "ingest_uploads_total", "Total uploads received", registry=ingest_registry
)
ingest_queue_depth = Gauge(
    "ingest_queue_depth", "Uploads waiting to be processed", registry=ingest_registry
)

recommendation_registry = CollectorRegistry()
recommendation_requests_total = Counter(
    "recommendation_requests_total", "Total recommendation requests", ["status"],
    registry=recommendation_registry,
)
recommendation_latency_seconds = Histogram(
    "recommendation_latency_seconds", "Recommendation latency", registry=recommendation_registry
)
