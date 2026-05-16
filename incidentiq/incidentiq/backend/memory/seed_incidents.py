"""
IncidentIQ - Seed Historical Incidents
Loads sample historical incidents into the vector store for demo/dev.
Run: python -m backend.memory.seed_incidents
"""
import logging
import os
from pathlib import Path

# Load .env so AWS credentials are available when run as __main__
_env = Path(__file__).parent.parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from backend.memory.vector_store import IncidentRecord, vector_store

logger = logging.getLogger(__name__)

SAMPLE_INCIDENTS = [
    IncidentRecord(
        incident_id="INC-2024-0311",
        title="Redis connection pool exhaustion causing API timeouts",
        description="Payment service API latency spiked to 8s p99. Redis connection pool exhausted due to connection leak in session handler.",
        root_cause="Connection leak in session_manager.py: connections not released on exception path.",
        mitigation="Increased pool size temporarily. Deployed fix to ensure connections released in finally block. Restarted payment-service pods.",
        severity="p1",
        service="payment-service",
        resolution_time_minutes=47,
        tags=["redis", "connection-pool", "latency", "payment"],
        timestamp="2024-03-11T14:22:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2024-0215",
        title="N+1 query causing database CPU spike on user-service",
        description="User service response time degraded from 120ms to 4.2s. Database CPU at 98%. Traced to ORM generating N+1 queries on user profile endpoint.",
        root_cause="Missing eager loading on user.orders relationship in UserProfileSerializer.",
        mitigation="Added select_related('orders') to queryset. Deployed hotfix. DB CPU returned to 12%.",
        severity="p2",
        service="user-service",
        resolution_time_minutes=31,
        tags=["database", "n+1", "orm", "performance", "cpu"],
        timestamp="2024-02-15T09:45:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2024-0401",
        title="Memory leak in notification worker causing OOM kills",
        description="Notification worker pods OOMKilled repeatedly. Memory grew from 256MB to 2GB over 6 hours. Traced to unbounded in-memory queue accumulation.",
        root_cause="Notification queue not bounded. Failed deliveries re-queued indefinitely without TTL.",
        mitigation="Added queue size limit and dead-letter queue. Rolled back to v2.1.3. Deployed fix in v2.1.4.",
        severity="p1",
        service="notification-service",
        resolution_time_minutes=62,
        tags=["memory-leak", "oom", "kubernetes", "queue", "worker"],
        timestamp="2024-04-01T03:10:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2024-0520",
        title="Cascading failure: auth-service timeout causing checkout failures",
        description="Checkout service 503 error rate reached 34%. Root cause: auth-service p99 latency at 12s due to expired TLS certificate on internal CA.",
        root_cause="Internal CA certificate expired. Auth service TLS handshake failing silently, causing timeouts.",
        mitigation="Renewed CA certificate. Restarted auth-service. Implemented certificate expiry alerting.",
        severity="p0",
        service="auth-service",
        resolution_time_minutes=28,
        tags=["tls", "certificate", "auth", "cascading-failure", "checkout"],
        timestamp="2024-05-20T11:30:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2024-0612",
        title="Deployment rollout caused 15% error rate spike on order-service",
        description="Order service error rate jumped from 0.1% to 15.3% immediately after v3.2.0 deployment. New database migration introduced breaking schema change.",
        root_cause="Migration removed non-nullable column still referenced by old pod replicas during rolling update.",
        mitigation="Rolled back to v3.1.9. Added backward-compatible migration strategy. Implemented blue-green deployment for schema changes.",
        severity="p1",
        service="order-service",
        resolution_time_minutes=19,
        tags=["deployment", "migration", "schema", "rollback", "rolling-update"],
        timestamp="2024-06-12T16:05:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2024-0708",
        title="Kafka consumer lag causing delayed order processing",
        description="Order processing delayed by 45+ minutes. Kafka consumer group lag reached 2.1M messages. Consumer threads blocked on downstream HTTP call with no timeout.",
        root_cause="Missing HTTP timeout on inventory-service client. Single slow response blocked all consumer threads.",
        mitigation="Added 5s timeout to inventory client. Scaled consumer group from 3 to 12 pods. Lag cleared in 22 minutes.",
        severity="p2",
        service="order-processor",
        resolution_time_minutes=55,
        tags=["kafka", "consumer-lag", "timeout", "threading", "inventory"],
        timestamp="2024-07-08T08:20:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2024-0819",
        title="S3 throttling causing image upload failures",
        description="Product image uploads failing with 503 SlowDown errors. S3 request rate exceeded 3,500 PUT/s limit on single prefix.",
        root_cause="All images stored under single S3 prefix /uploads/products/. High concurrency exceeded per-prefix rate limit.",
        mitigation="Implemented date-based prefix sharding (/uploads/YYYY/MM/DD/). Deployed fix. Error rate dropped to 0%.",
        severity="p2",
        service="media-service",
        resolution_time_minutes=38,
        tags=["s3", "throttling", "rate-limit", "prefix", "uploads"],
        timestamp="2024-08-19T13:55:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2024-0923",
        title="Deadlock in inventory service causing transaction failures",
        description="Inventory service transaction failure rate at 8%. Database deadlock detected between order reservation and stock update transactions.",
        root_cause="Two code paths acquiring row locks in opposite order: order_items then inventory vs inventory then order_items.",
        mitigation="Standardized lock acquisition order across all transaction paths. Added deadlock retry logic.",
        severity="p1",
        service="inventory-service",
        resolution_time_minutes=73,
        tags=["deadlock", "database", "transaction", "locking", "inventory"],
        timestamp="2024-09-23T20:15:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2024-1105",
        title="Rate limiter misconfiguration causing legitimate traffic rejection",
        description="API gateway rejecting 23% of valid requests with 429. Rate limiter config deployed with per-second limit instead of per-minute.",
        root_cause="Config value unit mismatch: 1000/min intended but deployed as 1000/sec which evaluated as ~16/sec.",
        mitigation="Corrected rate limit config. Redeployed API gateway. Added unit validation to config schema.",
        severity="p1",
        service="api-gateway",
        resolution_time_minutes=14,
        tags=["rate-limiting", "config", "api-gateway", "429"],
        timestamp="2024-11-05T10:40:00Z",
    ),
    IncidentRecord(
        incident_id="INC-2025-0117",
        title="Circuit breaker misconfigured causing retry storm",
        description="Recommendation service overwhelmed with 50x normal traffic. Circuit breaker threshold too high, allowing retry storms from 8 upstream services.",
        root_cause="Circuit breaker error threshold set to 80% (should be 50%). Upstream services retried aggressively before breaker opened.",
        mitigation="Lowered circuit breaker threshold to 50%. Added exponential backoff to all upstream clients. Deployed Resilience4j config update.",
        severity="p0",
        service="recommendation-service",
        resolution_time_minutes=41,
        tags=["circuit-breaker", "retry-storm", "resilience", "cascading-failure"],
        timestamp="2025-01-17T22:30:00Z",
    ),
]


def seed():
    """Seed the vector store with historical incidents."""
    logger.info("Seeding %d historical incidents into vector store...", len(SAMPLE_INCIDENTS))
    for incident in SAMPLE_INCIDENTS:
        try:
            doc_id = vector_store.upsert_incident(incident)
            logger.info("  ✓ Seeded: %s → %s", incident.incident_id, doc_id)
        except Exception as e:
            logger.error("  ✗ Failed to seed %s: %s", incident.incident_id, e)
    logger.info("Seeding complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
