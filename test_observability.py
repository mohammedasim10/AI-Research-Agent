"""
test_observability.py - Unit tests for Observability, Metrics, and /health Subsystem.
"""

import json
import logging
import time
import unittest
import urllib.request

from observability import (
    JSONFormatter,
    MetricsRegistry,
    HealthServer,
    create_request_context,
    trace_operation,
)


class TestObservability(unittest.TestCase):
    """Tests for structured logging, metrics aggregation, and health server."""

    def test_json_formatter(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="agent.py",
            lineno=42,
            msg="Agent execution started",
            args=(),
            exc_info=None,
        )
        record.request_id = "req-12345"
        record.user_id_masked = "98***21"
        record.action = "research_session"
        record.duration_ms = 150.5

        formatted_str = formatter.format(record)
        parsed = json.loads(formatted_str)

        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["message"], "Agent execution started")
        self.assertEqual(parsed["request_id"], "req-12345")
        self.assertEqual(parsed["user_id"], "98***21")
        self.assertEqual(parsed["action"], "research_session")
        self.assertEqual(parsed["duration_ms"], 150.5)

    def test_metrics_registry(self):
        metrics = MetricsRegistry()
        metrics.record_request(
            action="research_session",
            success=True,
            duration_seconds=2.5,
            model_name="gemini-2.5-flash",
            sources_count=5,
            citations_count=4,
            grounded_count=4,
        )
        metrics.record_request(
            action="research_session",
            success=False,
            duration_seconds=1.0,
            model_name="gemini-2.5-flash",
            sources_count=0,
            citations_count=0,
            grounded_count=0,
        )

        snapshot = metrics.get_snapshot()
        self.assertEqual(snapshot["total_requests"], 2)
        self.assertEqual(snapshot["successful_requests"], 1)
        self.assertEqual(snapshot["failed_requests"], 1)
        self.assertEqual(snapshot["success_rate_percent"], 50.0)
        self.assertEqual(snapshot["total_sources_retrieved"], 5)
        self.assertEqual(snapshot["grounding_accuracy_percent"], 100.0)

    def test_trace_operation_context_manager(self):
        with trace_operation("unit_test_op", user_id=123456789) as ctx:
            self.assertTrue(ctx.request_id.startswith("req-"))
            self.assertEqual(ctx.user_id_masked, "12***89")
            time.sleep(0.01)

    def test_health_server_endpoint(self):
        # Start server on dynamic test port
        test_port = 18088
        server = HealthServer(host="127.0.0.1", port=test_port)
        server.start()
        time.sleep(0.1)

        try:
            url = f"http://127.0.0.1:{test_port}/health"
            req = urllib.request.urlopen(url, timeout=3)
            data = json.loads(req.read().decode("utf-8"))

            self.assertIn("status", data)
            self.assertIn("checks", data)
            self.assertIn("metrics", data)
            self.assertEqual(data["service"], "ResearchAI Autonomous Orchestrator")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
