"""
personal_assistant.py - Telegram Personal Account AI Auto-Responder (Telethon MTProto).
Listens to incoming direct messages (DMs) sent to Mohammed Asim's personal Telegram account,
detects the sender's language/dialect, explains that Asim is currently unavailable and will ping them,
intelligently answers their questions, and logs all incoming messages.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Dict, Optional

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import User

# Load environment configuration
load_dotenv()

from bot import generate_conversational_reply
from config import config as app_config
from database import db
from utils.helpers import truncate_text

logging.basicConfig(
    format="%(asctime)s - [PersonalAssistant] - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ResearchAI.PersonalAssistant")

# Credentials for Telegram Client (from https://my.telegram.org)
API_ID = int(os.getenv("TELEGRAM_API_ID", "0").strip() or "0")
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "asim_personal_session").strip()
PHONE_NUMBER = os.getenv("TELEGRAM_PHONE", "").strip()

# Cooldown dictionary to avoid spamming the same user: user_id -> last_replied_timestamp
USER_REPLY_COOLDOWN: Dict[int, float] = {}
COOLDOWN_SECONDS = 120  # 2 minutes cooldown before repeating standard absence greeting


def create_client() -> TelegramClient:
    """Instantiates the Telethon Telegram Client."""
    if not API_ID or not API_HASH:
        raise ValueError(
            "Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env!\n"
            "Please obtain your free API ID and API HASH from https://my.telegram.org"
        )
    return TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def main():
    logger.info("Initializing Telegram Personal Account AI Auto-Responder...")
    client = create_client()

    if PHONE_NUMBER:
        await client.start(phone=PHONE_NUMBER)
    else:
        await client.start()

    me = await client.get_me()
    asim_id = me.id
    asim_username = me.username or me.first_name
    logger.info(f"✅ Connected to Telegram as: {me.first_name} (@{asim_username}) [ID: {asim_id}]")
    print("=" * 65)
    print(f"🤖 Personal Account AI Auto-Responder is ACTIVE for @{asim_username}")
    print("Listening for incoming private direct messages (DMs)...")
    print("=" * 65)

    @client.on(events.NewMessage(incoming=True))
    async def handle_incoming_dm(event: events.NewMessage.Event):
        # Only handle private 1-on-1 direct messages (ignore group chats and channels)
        if not event.is_private:
            return

        # Ignore messages sent by yourself or automated bots
        sender = await event.get_sender()
        if not sender or not isinstance(sender, User) or sender.is_self or sender.bot:
            return

        user_id = sender.id
        first_name = sender.first_name or "Friend"
        username = f"@{sender.username}" if sender.username else first_name
        message_text = event.raw_text.strip() if event.raw_text else ""

        if not message_text:
            return

        logger.info(f"📩 Incoming DM from {username} ({user_id}): {truncate_text(message_text, 60)}")

        # Log message into contact database
        db.log_contact_message(
            user_id=user_id,
            username=sender.username or "",
            name=f"{sender.first_name or ''} {sender.last_name or ''}".strip(),
            message=message_text,
        )

        # Show typing indicator
        async with client.action(event.chat_id, "typing"):
            await asyncio.sleep(1.2)  # Natural human-like pause

            # Generate intelligent response matching sender's language/dialect
            api_key = app_config.gemini_api_key or ""
            user_lang = db.get_user_setting(user_id, "language", "en")

            reply = await asyncio.to_thread(
                generate_conversational_reply,
                user_id=user_id,
                message=message_text,
                api_key=api_key,
                language=user_lang,
            )

            # Send reply directly in personal chat
            await event.reply(reply)
            logger.info(f"📤 Replied to {username}: {truncate_text(reply, 60)}")

    # Keep running indefinitely
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPersonal Assistant stopped.")
    except Exception as e:
        logger.error(f"Fatal error running Personal Assistant: {e}")
