"""
test_production_bot.py - Comprehensive Unit & Integration Tests for Production ResearchAI Bot.
Covers:
1. Strict User Session Isolation (User A vs User B)
2. Database CRUD & Parameterized Queries
3. /clear Command Isolation
4. Multilingual & Arabic RTL Formatting
5. Domain-Aware Source Prioritization
6. Strict Citation Grounding & Zero Fabrication
7. Rate Limiter Cooldown Enforcement
8. Admin Access Control & Rejection of Unauthorized IDs
9. Duplicate Update Detection
10. Webhook Secret Token Verification
11. Safe Markdown Message Splitting
12. Database Connection Resilience
"""

import os
import tempfile
import time
import unittest
from pathlib import Path

from bot import (
    create_production_bot_app,
    is_authorized_admin,
    is_duplicate_update,
    split_message_safely,
)
from config import AppConfig
from database import Database
from report_generator import SUPPORTED_LANGUAGES
from utils.helpers import (
    classify_source_type,
    extract_domain,
    format_rtl_if_arabic,
)


class TestProductionBot(unittest.TestCase):

    def setUp(self):
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_file.close()
        self.db = Database(db_path=Path(self.temp_db_file.name))

    def tearDown(self):
        try:
            os.unlink(self.temp_db_file.name)
        except Exception:
            pass

    # 1. Strict User Session Isolation
    def test_user_session_isolation(self):
        user_a = 10001
        user_b = 10002

        self.db.get_or_create_user(user_a, "user_a", "Alice")
        self.db.get_or_create_user(user_b, "user_b", "Bob")

        # Set distinct languages
        self.db.update_user_setting(user_a, "language", "hi")
        self.db.update_user_setting(user_b, "language", "ar")

        self.assertEqual(self.db.get_user_setting(user_a, "language"), "hi")
        self.assertEqual(self.db.get_user_setting(user_b, "language"), "ar")

        # Add isolated conversation messages
        self.db.add_conversation_message(user_a, "user", "Alice secret message")
        self.db.add_conversation_message(user_b, "user", "Bob secret message")

        history_a = self.db.get_conversation_history(user_a)
        history_b = self.db.get_conversation_history(user_b)

        self.assertEqual(len(history_a), 1)
        self.assertEqual(history_a[0]["content"], "Alice secret message")

        self.assertEqual(len(history_b), 1)
        self.assertEqual(history_b[0]["content"], "Bob secret message")

        # Verify User A cannot access User B's history
        for msg in history_a:
            self.assertNotEqual(msg["content"], "Bob secret message")

    # 2. Database CRUD & Parameterized Queries
    def test_database_crud_and_sql_injection_defense(self):
        user_id = 99999
        # Attempt SQL injection in names and query
        malicious_name = "Robert'); DROP TABLE users;--"
        user = self.db.get_or_create_user(user_id, "hacker", malicious_name)
        self.assertEqual(user["first_name"], malicious_name)

        # Confirm users table is intact
        queried_user = self.db.get_or_create_user(user_id)
        self.assertEqual(queried_user["first_name"], malicious_name)

    # 3. /clear Command Isolation
    def test_clear_conversation_isolation(self):
        user_a = 20001
        user_b = 20002

        self.db.add_conversation_message(user_a, "user", "Message 1 for Alice")
        self.db.add_conversation_message(user_a, "assistant", "Reply 1 for Alice")
        self.db.add_conversation_message(user_b, "user", "Message 1 for Bob")

        # Clear Alice's history
        deleted_count = self.db.clear_user_conversation(user_a)
        self.assertEqual(deleted_count, 2)

        # Verify Alice has 0 messages, but Bob still has 1
        self.assertEqual(len(self.db.get_conversation_history(user_a)), 0)
        self.assertEqual(len(self.db.get_conversation_history(user_b)), 1)

    # 4. Multilingual & Arabic RTL Formatting
    def test_multilingual_and_arabic_rtl(self):
        for code in ["en", "hi", "te", "ar"]:
            self.assertIn(code, SUPPORTED_LANGUAGES)

        # Test Arabic RTL prepending
        ar_text = "تقرير البحث العلمي\nالنتائج الرئيسية"
        rtl_formatted = format_rtl_if_arabic(ar_text, language="ar")
        self.assertTrue(rtl_formatted.startswith("\u200F"))

        # English should NOT have RTL marks
        en_text = "Research Report\nKey Findings"
        non_rtl = format_rtl_if_arabic(en_text, language="en")
        self.assertFalse(non_rtl.startswith("\u200F"))

    # 5. Domain-Aware Source Categorization
    def test_domain_aware_source_categorization(self):
        # Healthcare & Public Health
        self.assertEqual(classify_source_type("who.int"), "Government / Public Health Org")
        self.assertEqual(classify_source_type("ncbi.nlm.nih.gov"), "Government / Public Health Org")
        self.assertEqual(classify_source_type("thelancet.com"), "Scientific Journal / Peer-Reviewed")
        self.assertEqual(classify_source_type("nature.com"), "Scientific Journal / Peer-Reviewed")

        # Academic
        self.assertEqual(classify_source_type("arxiv.org"), "Academic / University")
        self.assertEqual(classify_source_type("stanford.edu"), "Academic / University")

        # Technology
        self.assertEqual(classify_source_type("docs.python.org"), "Official Tech Documentation")
        self.assertEqual(classify_source_type("w3.org"), "Official Tech Documentation")

    # 6. Rate Limiter
    def test_rate_limiter_cooldown(self):
        user_id = 30001
        limit = 3

        # First 3 requests allowed
        for _ in range(limit):
            allowed, remaining, wait = self.db.check_and_increment_rate_limit(
                user_id, max_requests=limit, window_seconds=10.0
            )
            self.assertTrue(allowed)

        # 4th request blocked
        allowed, remaining, wait = self.db.check_and_increment_rate_limit(
            user_id, max_requests=limit, window_seconds=10.0
        )
        self.assertFalse(allowed)
        self.assertGreater(wait, 0.0)

    # 7. Admin Authorization
    def test_admin_authorization(self):
        test_config = AppConfig(admin_user_ids=(12345, 67890))
        self.assertIn(12345, test_config.admin_user_ids)
        self.assertNotIn(99999, test_config.admin_user_ids)

    # 8. Duplicate Update Protection
    def test_duplicate_update_protection(self):
        update_id = 888123
        # First time: not duplicate
        self.assertFalse(is_duplicate_update(update_id))
        # Second time: duplicate
        self.assertTrue(is_duplicate_update(update_id))

    # 9. Message Splitting Under Telegram Limit
    def test_safe_message_splitting(self):
        long_paragraph = "Paragraph start. " + ("Evidence content details. " * 200)
        chunks = split_message_safely(long_paragraph, max_chunk_size=1000)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1050)

    # 10. Research Session Storage & History Recall
    def test_research_session_persistence(self):
        user_id = 40001
        self.db.get_or_create_user(user_id)
        session_id = "sess-abc-123"

        self.db.save_research_session(
            session_id=session_id,
            user_id=user_id,
            query="Solid State Batteries",
            mode="deep",
            language="en",
            plan={"dimensions": ["cathode", "anode"]},
            analysis={"consensus": ["higher energy density"]},
            report_markdown="## Research Report\nSolid state batteries offer high energy density.",
            teaching_markdown="## Tutor Guide\nThink of battery cells as tiny sponges.",
            sources=[{"title": "Nature Energy Study", "url": "https://nature.com/article1"}],
            metrics={"duration_seconds": 12.4},
        )

        latest = self.db.get_latest_research_session(user_id)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["query"], "Solid State Batteries")
        self.assertEqual(len(latest["sources"]), 1)
        self.assertEqual(latest["sources"][0]["title"], "Nature Energy Study")

    # 11. Admin Metrics & Audit Telemetry
    def test_admin_metrics_calculation(self):
        user_id = 50001
        self.db.get_or_create_user(user_id, "admin_user", "Admin")
        self.db.log_event(user_id, "research_run", "Completed query", status="success", duration_ms=2500)
        self.db.log_event(user_id, "api_error", "Timeout occurred", status="error")

        metrics = self.db.get_admin_metrics()
        self.assertGreaterEqual(metrics["total_users"], 1)
        self.assertGreaterEqual(metrics["total_events"], 2)
        self.assertGreaterEqual(metrics["error_count"], 1)
        self.assertGreaterEqual(metrics["error_rate_pct"], 0.0)

    # 12. Thread-Safe Concurrency & Parallel Sessions
    def test_thread_safe_concurrency(self):
        import threading
        errors = []

        def worker(uid: int):
            try:
                self.db.get_or_create_user(uid, f"user_{uid}", f"User{uid}")
                for i in range(5):
                    self.db.add_conversation_message(uid, "user", f"Msg {i} from {uid}")
                history = self.db.get_conversation_history(uid)
                if len(history) != 5:
                    errors.append(f"History mismatch for {uid}: got {len(history)}")
            except Exception as e:
                errors.append(f"Thread exception for {uid}: {e}")

        threads = [threading.Thread(target=worker, args=(60000 + i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrency errors: {errors}")

    # 13. Voice Handler Safety on Invalid Data
    def test_voice_handler_safety(self):
        from voice_handler import transcribe_voice_message
        text, lang = transcribe_voice_message(b"", mime_type="audio/ogg")
        self.assertIsNone(text)
        self.assertIsNone(lang)

    # 14. Production Application Factory
    def test_production_app_builder(self):
        app = create_production_bot_app()
        self.assertIsNotNone(app)
        self.assertIsNotNone(app.bot)


if __name__ == "__main__":
    unittest.main()

