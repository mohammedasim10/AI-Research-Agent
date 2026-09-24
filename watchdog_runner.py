"""
watchdog_runner.py - 24/7 Self-Healing Process Supervisor for ResearchAI.
Ensures continuous, uninterrupted 24/7 uptime for the Telegram AI Assistant.
Monitors child process health, automatically recovers from network disconnects or crashes,
and logs uptime telemetry.
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
import urllib.request

logging.basicConfig(
    format="%(asctime)s - [24/7 Watchdog] - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ResearchAI.Watchdog")

# Health check settings
HEALTH_URL = "http://127.0.0.1:8080/health"
HEALTH_CHECK_INTERVAL_SECONDS = 30
MAX_CONSECUTIVE_FAILURES = 3
RESTART_BACKOFF_SECONDS = 5


def check_bot_health() -> bool:
    """Queries the internal /health endpoint to verify bot responsiveness."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=6) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_supervisor():
    """Main self-healing supervisor loop."""
    print("=" * 70)
    print("🛡️  ResearchAI 24/7 Live Automation Supervisor Starting...")
    print(f"🕒  Started At: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    restart_count = 0

    while True:
        logger.info(f"🚀 Launching Telegram Bot process (Start Count: {restart_count + 1})...")
        cmd = [sys.executable, "bot.py"]

        process = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            env=os.environ.copy(),
        )

        logger.info(f"🟢 Telegram Bot process active (PID: {process.pid}). Entering health watch loop...")
        consecutive_health_failures = 0

        # Wait initial warmup period before health probes
        time.sleep(10)

        while True:
            # Check if process exited on its own
            ret_code = process.poll()
            if ret_code is not None:
                logger.warning(f"⚠️ Telegram Bot process terminated with exit code: {ret_code}")
                break

            # Perform periodic health inspection
            is_healthy = check_bot_health()
            if is_healthy:
                consecutive_health_failures = 0
            else:
                consecutive_health_failures += 1
                logger.warning(
                    f"⚠️ Health probe failed ({consecutive_health_failures}/{MAX_CONSECUTIVE_FAILURES})"
                )
                if consecutive_health_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error("❌ Consecutive health checks failed. Terminating unresponsive process for recovery...")
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except Exception:
                        process.kill()
                    break

            time.sleep(HEALTH_CHECK_INTERVAL_SECONDS)

        restart_count += 1
        logger.info(f"🔄 Auto-recovery triggered. Restarting bot in {RESTART_BACKOFF_SECONDS}s...")
        time.sleep(RESTART_BACKOFF_SECONDS)


if __name__ == "__main__":
    try:
        run_supervisor()
    except KeyboardInterrupt:
        logger.info("Supervisor stopped by operator.")
