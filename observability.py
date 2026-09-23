"""
observability.py - Production Observability, Structured Logging, Metrics & Health Subsystem.
Provides correlation-tracked JSON logging, performance telemetry, audit logs,
and an embedded HTTP /health inspection server.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import logging
import os
import socket
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

from utils.security import mask_user_id

logger = logging.getLogger("researchai.observability")


@dataclass
class RequestContext:
    """Carries correlation ID and tracing context for a single user/agent workflow."""
    request_id: str
    user_id_masked: str
    action: str
    started_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def elapsed_ms(self) -> float:
        return round((time.time() - self.started_at) * 1000, 2)


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON documents for ingest by Datadog, CloudWatch, ELK."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        
        # Merge custom attributes
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "user_id_masked"):
            log_data["user_id"] = record.user_id_masked
        if hasattr(record, "action"):
            log_data["action"] = record.action
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "extra_payload"):
            log_data["extra"] = record.extra_payload

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class MetricsRegistry:
    """In-memory thread-safe operational metrics collector."""

    def __init__(self):
        self._lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_citations_verified = 0
        self.grounded_citations_count = 0
        self.total_latency_seconds = 0.0
        self.model_calls_by_name: Dict[str, int] = {}
        self.requests_by_action: Dict[str, int] = {}
        self.sources_retrieved_total = 0

    def record_request(
        self,
        action: str,
        success: bool,
        duration_seconds: float,
        model_name: Optional[str] = None,
        sources_count: int = 0,
        citations_count: int = 0,
        grounded_count: int = 0,
    ) -> None:
        with self._lock:
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1

            self.total_latency_seconds += duration_seconds
            self.sources_retrieved_total += sources_count
            self.total_citations_verified += citations_count
            self.grounded_citations_count += grounded_count

            self.requests_by_action[action] = self.requests_by_action.get(action, 0) + 1
            if model_name:
                self.model_calls_by_name[model_name] = self.model_calls_by_name.get(model_name, 0) + 1

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            avg_lat = round(self.total_latency_seconds / self.total_requests, 2) if self.total_requests > 0 else 0.0
            sr = round((self.successful_requests / self.total_requests) * 100, 2) if self.total_requests > 0 else 100.0
            gr = round((self.grounded_citations_count / self.total_citations_verified) * 100, 2) if self.total_citations_verified > 0 else 100.0
            return {
                "started_at": self.started_at,
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate_percent": sr,
                "average_latency_seconds": avg_lat,
                "total_sources_retrieved": self.sources_retrieved_total,
                "total_citations_verified": self.total_citations_verified,
                "grounding_accuracy_percent": gr,
                "model_calls": dict(self.model_calls_by_name),
                "action_counts": dict(self.requests_by_action),
            }


metrics_registry = MetricsRegistry()


def create_request_context(action: str, user_id: Any = None, **kwargs) -> RequestContext:
    """Generates a new correlation context for an incoming task."""
    req_id = f"req-{uuid.uuid4().hex[:12]}"
    masked_user = mask_user_id(user_id)
    return RequestContext(
        request_id=req_id,
        user_id_masked=masked_user,
        action=action,
        metadata=kwargs,
    )


@contextmanager
def trace_operation(action: str, user_id: Any = None, **metadata):
    """Context manager for tracing latency and outcome of operations."""
    ctx = create_request_context(action, user_id, **metadata)
    logger.info(
        f"Started action '{action}'",
        extra={
            "request_id": ctx.request_id,
            "user_id_masked": ctx.user_id_masked,
            "action": action,
            "extra_payload": metadata,
        },
    )
    t0 = time.time()
    success = True
    err_str = None
    try:
        yield ctx
    except Exception as exc:
        success = False
        err_str = str(exc)
        raise
    finally:
        dur_sec = time.time() - t0
        dur_ms = round(dur_sec * 1000, 2)
        metrics_registry.record_request(
            action=action,
            success=success,
            duration_seconds=dur_sec,
        )
        level = logging.INFO if success else logging.ERROR
        logger.log(
            level,
            f"Finished action '{action}' in {dur_ms}ms (success={success})" + (f": {err_str}" if err_str else ""),
            extra={
                "request_id": ctx.request_id,
                "user_id_masked": ctx.user_id_masked,
                "action": action,
                "duration_ms": dur_ms,
                "success": success,
                "error": err_str,
            },
        )


class HealthHttpHandler(BaseHTTPRequestHandler):
    """HTTP request handler providing JSON /health endpoint."""

    def do_GET(self):
        if self.path in ("/health", "/", "/metrics"):
            from database import db
            # Check DB health
            db_healthy = False
            try:
                stats = db.get_stats()
                db_healthy = isinstance(stats, dict) and "total_users" in stats
            except Exception as db_err:
                logger.debug(f"Health DB check failed: {db_err}")
                db_healthy = False

            # Check API key configuration
            from config import config
            api_key_set = bool(config.gemini_api_key)

            overall_status = "healthy" if (db_healthy and api_key_set) else ("degraded" if db_healthy else "unhealthy")
            
            payload = {
                "status": overall_status,
                "service": "ResearchAI Autonomous Orchestrator",
                "version": "2.0.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": {
                    "database_sqlite_wal": "connected" if db_healthy else "error",
                    "gemini_api_key": "configured" if api_key_set else "missing",
                    "model": config.gemini_model,
                },
                "metrics": metrics_registry.get_snapshot(),
            }

            resp_bytes = json.dumps(payload, indent=2).encode("utf-8")
            status_code = 200 if db_healthy else 503
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}')

    def log_message(self, format, *args):
        # Silence default access logging to stderr
        pass


class HealthServer:
    """Embedded non-blocking HTTP health check server."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts health server in background thread."""
        try:
            self.server = HTTPServer((self.host, self.port), HealthHttpHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="HealthServerThread")
            self.thread.start()
            logger.info(f"Observability health server listening on http://{self.host}:{self.port}/health")
        except Exception as e:
            logger.warning(f"Could not start health server on port {self.port}: {e}")

    def stop(self) -> None:
        """Stops the health server gracefully."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Health server stopped.")
