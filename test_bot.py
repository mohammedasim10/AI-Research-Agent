"""
test_bot.py - Unit tests for Telegram Bot modules and utilities.
"""

import os
import unittest
from bot import (
    split_markdown_message,
    load_user_prefs,
    save_user_prefs,
    get_user_config,
    update_user_config,
    create_telegram_bot_app,
)


class TestTelegramBot(unittest.TestCase):

    def test_split_markdown_message_short(self):
        short_text = "Hello world! This is a simple test."
        chunks = split_markdown_message(short_text, max_chunk_size=100)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], short_text)

    def test_split_markdown_message_long(self):
        paragraphs = [f"Section {i}\n" + ("Lorem ipsum dolor sit amet. " * 20) for i in range(10)]
        full_text = "\n\n".join(paragraphs)
        chunks = split_markdown_message(full_text, max_chunk_size=500)
        self.assertGreater(len(chunks), 1)
        # All alphanumeric characters preserved
        joined_clean = "".join(c for chunk in chunks for c in chunk if c.isalnum())
        full_clean = "".join(c for c in full_text if c.isalnum())
        self.assertEqual(joined_clean, full_clean)

    def test_user_prefs_management(self):
        import time
        test_uid = int(time.time() * 1000) % 100000000
        cfg = get_user_config(test_uid)
        self.assertIn("language", cfg)
        self.assertEqual(cfg["language"], "en")

        update_user_config(test_uid, "language", "hi")
        cfg_updated = get_user_config(test_uid)
        self.assertEqual(cfg_updated["language"], "hi")

        update_user_config(test_uid, "gemini_api_key", "test_key_1234567890")
        self.assertEqual(get_user_config(test_uid)["gemini_api_key"], "test_key_1234567890")

    def test_app_builder(self):
        app = create_telegram_bot_app()
        self.assertIsNotNone(app)
        self.assertIsNotNone(app.bot)


if __name__ == "__main__":
    unittest.main()
