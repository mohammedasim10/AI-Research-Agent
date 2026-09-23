"""
bot.py - Production-Grade Telegram AI Research Assistant.
Provides enterprise-grade autonomous multi-stage research, verifiable citation synthesis,
isolated user sessions, multilingual support (EN, HI, TE, AR with RTL), voice processing,
per-user rate limiting, duplicate update protection, and secure admin telemetry.
"""

import asyncio
import io
import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Load environment
load_dotenv()

# Import core modules
from agent import ResearchAgent, ResearchSessionResult
from config import AppConfig, config as default_config
from database import db
from report_generator import SUPPORTED_LANGUAGES
from utils.helpers import clean_text, format_rtl_if_arabic, truncate_text
from voice_handler import transcribe_voice_message

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ResearchAI.Bot")

# In-memory tracking of active tasks & processed updates (for idempotency & rate defense)
ACTIVE_RESEARCH_LOCKS: Dict[int, bool] = {}
PROCESSED_UPDATE_IDS: set = set()
MAX_PROCESSED_UPDATE_CACHE = 10000


def is_duplicate_update(update_id: int) -> bool:
    """Guards against duplicate Telegram webhook deliveries."""
    if update_id in PROCESSED_UPDATE_IDS:
        return True
    PROCESSED_UPDATE_IDS.add(update_id)
    if len(PROCESSED_UPDATE_IDS) > MAX_PROCESSED_UPDATE_CACHE:
        # Prune oldest
        try:
            for _ in range(1000):
                PROCESSED_UPDATE_IDS.pop()
        except KeyError:
            pass
    return False


def is_authorized_admin(user_id: int) -> bool:
    """Verifies whether a user is an authorized admin in config."""
    return user_id in default_config.admin_user_ids


def get_effective_user_api_key(user_id: int) -> Optional[str]:
    """Retrieves user-specific API key override or falls back to system default."""
    custom_key = db.get_user_setting(user_id, "custom_api_key")
    return custom_key or default_config.gemini_api_key


def get_user_config(user_id: int) -> Dict[str, Any]:
    """Backward-compatible user preference getter backed by SQLite database."""
    user = db.get_or_create_user(user_id)
    return {
        "language": user.get("language", "en"),
        "mode": user.get("response_mode", "deep"),
        "gemini_api_key": user.get("custom_api_key"),
        "voice_enabled": user.get("voice_enabled", 1),
    }


def update_user_config(user_id: int, key: str, value: Any) -> None:
    """Backward-compatible user preference setter backed by SQLite database."""
    if key == "gemini_api_key":
        key = "custom_api_key"
    elif key == "mode":
        key = "response_mode"
    db.update_user_setting(user_id, key, value)




# ==============================================================================
# Live Research Progress Tracker
# ==============================================================================

class LiveProgressTracker:
    """
    Manages throttled, verifiable status updates in Telegram corresponding to actual
    research pipeline execution milestones.
    """

    STAGE_EMOJIS = {
        "plan": "🔎",
        "search": "🌐",
        "fetch": "📚",
        "analyze": "⚖️",
        "report": "✍️",
        "complete": "✅",
        "error": "❌",
    }

    STAGE_LABELS = {
        "plan": "Understanding & Planning Strategy",
        "search": "Searching Authoritative Sources",
        "fetch": "Extracting Evidence & Clean Text",
        "analyze": "Cross-Checking & Fact Verification",
        "report": "Synthesizing Structured Report",
    }

    def __init__(self, bot, chat_id: int, message_id: int, question: str, mode: str, language: str, loop: asyncio.AbstractEventLoop):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.question = question
        self.mode = mode
        self.language = language
        self.loop = loop
        self.last_update_time = 0.0
        self.min_interval = 1.3  # seconds between edits
        self.current_stage = "plan"

    def on_progress(self, stage: str, status: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Callback invoked synchronously from ResearchAgent.run."""
        self.current_stage = stage
        now = time.time()
        if (now - self.last_update_time >= self.min_interval) or status in ("completed", "failed"):
            self.last_update_time = now
            text = self._build_status_text(stage, message)
            asyncio.run_coroutine_threadsafe(self._async_edit(text), self.loop)

    def _build_status_text(self, current_stage: str, current_msg: str) -> str:
        mode_str = "🔬 Deep Research" if self.mode == "deep" else "⚡ Quick Answer"
        stages = ["plan", "search", "fetch", "analyze", "report"]
        
        lines = []
        for s in stages:
            emoji = self.STAGE_EMOJIS.get(s, "•")
            label = self.STAGE_LABELS.get(s, s.title())
            if s == current_stage:
                lines.append(f"▶️ **{emoji} {label}** *(in progress...)*")
            elif stages.index(s) < stages.index(current_stage) if current_stage in stages else False:
                lines.append(f"✓ {label}")
            else:
                lines.append(f"○ {label}")

        pipeline_block = "\n".join(lines)
        return (
            f"🤖 **ResearchAI Assistant** | {mode_str}\n"
            f"🎯 **Topic**: _{truncate_text(self.question, 100)}_\n\n"
            f"**Research Progress:**\n{pipeline_block}\n\n"
            f"💡 `{current_msg}`"
        )

    async def _async_edit(self, text: str):
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except BadRequest as be:
            if "Message is not modified" not in str(be):
                try:
                    clean = text.replace("**", "").replace("*", "").replace("`", "").replace("_", "")
                    await self.bot.edit_message_text(
                        chat_id=self.chat_id,
                        message_id=self.message_id,
                        text=clean,
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Progress update edit error: {e}")


# ==============================================================================
# Helper Functions: Safe Message Splitting & Transmission
# ==============================================================================

def split_message_safely(text: str, max_chunk_size: int = 3800) -> List[str]:
    """
    Splits long Markdown content cleanly on paragraph, heading, and word boundaries,
    strictly respecting Telegram's 4096 character limit.
    """
    if not text:
        return [""]

    if len(text) <= max_chunk_size:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for line in text.split("\n"):
        line_len = len(line) + 1
        if line_len > max_chunk_size:
            # Flush accumulated lines
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            # Split this massive line across word boundaries
            words = line.split(" ")
            sub_line: List[str] = []
            sub_len = 0
            for w in words:
                w_len = len(w) + 1
                if sub_len + w_len > max_chunk_size and sub_line:
                    chunks.append(" ".join(sub_line))
                    sub_line = [w]
                    sub_len = w_len
                else:
                    sub_line.append(w)
                    sub_len += w_len
            if sub_line:
                current.append(" ".join(sub_line))
                current_len += len(" ".join(sub_line)) + 1
        elif current_len + line_len > max_chunk_size and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


async def safe_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode=constants.ParseMode.MARKDOWN,
    language: str = "en",
) -> Any:
    """Transmits messages with Arabic RTL handling and safe plain-text fallback."""
    formatted_text = format_rtl_if_arabic(text, language)
    try:
        return await context.bot.send_message(
            chat_id=chat_id,
            text=formatted_text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
    except BadRequest as be:
        logger.warning(f"Markdown send failed: {be}. Falling back to plain text.")
        clean = formatted_text.replace("**", "").replace("*", "").replace("`", "").replace("_", "")
        return await context.bot.send_message(
            chat_id=chat_id,
            text=clean,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )


# ==============================================================================
# Conversational Personal Assistant Engine
# ==============================================================================

def generate_conversational_reply(user_id: int, message: str, api_key: str, language: str) -> str:
    """
    Generates an intelligent conversational response matching the user's dialect and language,
    acting as Mohammed Asim's personal AI Assistant.
    """
    history = db.get_conversation_history(user_id, limit=8)
    conv_context = ""
    for h in history:
        role = "User" if h["role"] == "user" else "Assistant"
        conv_context += f"{role}: {h['content']}\n"
    conv_context += f"User: {message}\nAssistant:"

    system_prompt = f"""You are the intelligent, polite, and articulate AI Research Assistant representing Mohammed Asim (@Asimm07), a dedicated student and researcher of Artificial Intelligence & Machine Learning (AI/ML).

CORE BEHAVIOR & RULES:
1. IDENTITY:
   - If someone asks for Asim or messages him: Politely explain that Asim is not available right now, and that you will ping/notify him as soon as he is free.
   - Offer to assist them, answer their questions, or take down a message for Asim.

2. MULTILINGUAL & DIALECT MATCHING:
   - Always match the user's exact language and dialect:
     * Roman Urdu / Roman English / Hinglish: Reply in fluent, polite Roman Urdu/English (e.g. "Salam! Main Asim ka AI Assistant hoon. Asim abhi available nahi hain, main aapko text ping kar doongi jab voh free honge. Aap batayein main aapki kya madad kar sakti hoon?").
     * Urdu (اردو script): Reply in formal, eloquent Urdu.
     * English: Reply in clear, professional, warm English.
     * Hindi (हिन्दी): Reply in Hindi script.
     * Telugu (తెలుగు): Reply in Telugu script.
     * Arabic (العربية): Reply in Modern Standard Arabic.

3. CAPABILITIES:
   - You can chat casually, answer science/AI/tech/math/coding questions, or take contact notes.
   - For full multi-source live web investigations, invite the user to use `/research <topic>` or `/quick <topic>`.
"""
    full_prompt = f"{system_prompt}\n\nRecent Conversation:\n{conv_context}"
    candidate_models = [default_config.gemini_model, "gemini-flash-latest", "gemma-4-26b-a4b-it", "gemma-4-31b-it", "gemini-2.5-flash"]

    for m in candidate_models:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            res = client.models.generate_content(
                model=m,
                contents=full_prompt,
                config={"temperature": 0.4},
            )
            if res and res.text:
                reply = res.text.strip()
                db.add_conversation_message(user_id, "user", message)
                db.add_conversation_message(user_id, "assistant", reply)
                return reply
        except Exception as e:
            logger.debug(f"Conversational model {m} error: {e}")

        try:
            import google.generativeai as genai_classic
            genai_classic.configure(api_key=api_key)
            model = genai_classic.GenerativeModel(model_name=m)
            res = model.generate_content(full_prompt)
            if res and res.text:
                reply = res.text.strip()
                db.add_conversation_message(user_id, "user", message)
                db.add_conversation_message(user_id, "assistant", reply)
                return reply
        except Exception as e_classic:
            logger.debug(f"Classic conversational model {m} error: {e_classic}")

    fallback_reply = (
        "Salam / Hello! I am Mohammed Asim's AI Assistant. "
        "Asim is not available right now, but I will ping you as soon as he is free. "
        "I have noted your message. Let me know if you would like me to answer any questions or research a topic for you!"
    )
    db.add_conversation_message(user_id, "user", message)
    db.add_conversation_message(user_id, "assistant", fallback_reply)
    return fallback_reply


# ==============================================================================
# Research Execution Engine (Deep Research & Quick Answers)
# ==============================================================================

async def execute_research_pipeline(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    question: str,
    mode: str = "deep",
    teach_only: bool = False,
) -> None:
    """
    Core executor for autonomous research with strict session isolation,
    live verifiable progress updates, multi-source fact checking, and document exports.
    """
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    user_id = user.id
    chat_id = chat.id
    clean_q = question.strip()

    if not clean_q:
        await safe_send(context, chat_id, "⚠️ Please provide a research question or topic! Example: `/research Solid-state battery commercialization timelines`")
        return

    # Rate Limiting Check
    allowed, remaining, retry_after = db.check_and_increment_rate_limit(
        user_id,
        max_requests=default_config.rate_limit_per_minute,
        window_seconds=60.0,
    )
    if not allowed:
        await safe_send(
            context,
            chat_id,
            f"⏳ **Rate Limit Reached**: You are making requests too quickly. Please wait `{retry_after}s` before submitting another research query.",
        )
        return

    # User active lock
    if ACTIVE_RESEARCH_LOCKS.get(user_id, False):
        await safe_send(
            context,
            chat_id,
            "⏳ You currently have an active research task running! Please wait for it to complete.",
        )
        return

    api_key = get_effective_user_api_key(user_id)
    if not api_key:
        await safe_send(
            context,
            chat_id,
            "🔑 **Gemini API Key Required**\n\n"
            "To perform live autonomous research, please configure your API key:\n"
            "1. Get a free key at [Google AI Studio](https://aistudio.google.com/app/apikey)\n"
            "2. Send `/setkey YOUR_KEY_HERE`\n",
        )
        return

    ACTIVE_RESEARCH_LOCKS[user_id] = True
    user_lang = db.get_user_setting(user_id, "language", "en")
    start_time = time.time()

    # Send initial status message
    initial_msg = await safe_send(
        context,
        chat_id,
        f"🤖 **ResearchAI Assistant Initializing...**\n"
        f"🎯 **Topic**: _{truncate_text(clean_q, 100)}_\n\n"
        f"🔎 *Formulating research strategy and search angles...*",
        language=user_lang,
    )

    loop = asyncio.get_running_loop()
    tracker = LiveProgressTracker(
        bot=context.bot,
        chat_id=chat_id,
        message_id=initial_msg.message_id,
        question=clean_q,
        mode=mode,
        language=user_lang,
        loop=loop,
    )

    def run_agent() -> ResearchSessionResult:
        agent = ResearchAgent(api_key=api_key, config=default_config)
        return agent.run(
            question=clean_q,
            language=user_lang,
            mode=mode,
            on_progress=tracker.on_progress,
        )

    try:
        session_result: ResearchSessionResult = await asyncio.to_thread(run_agent)
        duration_ms = (time.time() - start_time) * 1000.0

        if not session_result.success:
            err = session_result.error_message or "Unable to retrieve reliable sources."
            db.log_event(user_id, "research_run", f"Failed: {err}", status="failed", duration_ms=duration_ms)
            await safe_send(context, chat_id, f"❌ **Research Incomplete**: {err}\n\nIf reliable information could not be confirmed across sources, please try rephrasing your topic.")
            return

        # Persist session to isolated SQLite database
        session_id = str(uuid.uuid4())
        db.save_research_session(
            session_id=session_id,
            user_id=user_id,
            query=clean_q,
            mode=mode,
            language=user_lang,
            plan=session_result.plan,
            analysis=session_result.analysis,
            report_markdown=session_result.report_markdown,
            teaching_markdown=session_result.teaching_markdown,
            sources=session_result.sources,
            metrics=session_result.metrics,
        )
        db.log_event(user_id, "research_run", f"Success ({len(session_result.sources)} sources)", status="success", duration_ms=duration_ms)

        # Delete progress tracker message
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=initial_msg.message_id)
        except Exception:
            pass

        # Prepare header & content
        if teach_only:
            main_body = session_result.teaching_markdown or session_result.report_markdown
            header = f"🎓 **Understand This Topic: {clean_q}**\n\n"
        elif mode == "simple":
            main_body = session_result.teaching_markdown or session_result.report_markdown
            header = f"⚡ **Quick Answer: {clean_q}**\n\n"
        else:
            main_body = session_result.report_markdown
            header = f"🔬 **Research Dossier: {clean_q}**\n\n"

        full_text = header + main_body
        chunks = split_message_safely(full_text, max_chunk_size=3800)

        for i, chunk in enumerate(chunks):
            keyboard = None
            if i == len(chunks) - 1:
                buttons = []
                if not teach_only and session_result.teaching_markdown:
                    buttons.append(InlineKeyboardButton("🎓 Tutor Guide", callback_data=f"show_teach_{session_id}"))
                if session_result.sources:
                    buttons.append(InlineKeyboardButton("📚 Sources Cited", callback_data=f"show_sources_{session_id}"))
                if buttons:
                    keyboard = InlineKeyboardMarkup([buttons])

            await safe_send(context, chat_id, chunk, reply_markup=keyboard, language=user_lang)

        # Send full document as a .md file attachment
        clean_fn = "".join(c for c in clean_q[:25] if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        doc_filename = f"Research_{clean_fn}_{user_lang}.md"
        doc_bytes = io.BytesIO(full_text.encode("utf-8"))
        doc_bytes.name = doc_filename

        src_count = len(session_result.sources)
        duration_s = session_result.metrics.get("duration_seconds", round(duration_ms / 1000.0, 1))
        caption = f"📄 **Research Dossier Document**\n⏱️ Duration: {duration_s}s | 🌐 Verified Sources: {src_count}"

        try:
            await context.bot.send_document(
                chat_id=chat_id,
                document=doc_bytes,
                caption=caption,
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except Exception as doc_err:
            logger.debug(f"Document upload optional warning: {doc_err}")

    except Exception as exc:
        logger.exception("Unexpected error during research execution:")
        db.log_event(user_id, "research_run", str(exc), status="error")
        await safe_send(
            context,
            chat_id,
            "❌ Something went wrong while processing your research request. Please try again or rephrase your topic.",
        )
    finally:
        ACTIVE_RESEARCH_LOCKS[user_id] = False


# ==============================================================================
# Command Handlers
# ==============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /start command with an elegant, professional dashboard."""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    user_lang = db.get_user_setting(user.id, "language", "en")

    keyboard = [
        [
            InlineKeyboardButton("🔬 Deep Research", callback_data="nav_research"),
            InlineKeyboardButton("⚡ Quick Answer", callback_data="nav_quick"),
        ],
        [
            InlineKeyboardButton("📚 Sources", callback_data="nav_sources"),
            InlineKeyboardButton("🌐 Language", callback_data="nav_language"),
        ],
        [
            InlineKeyboardButton("🔊 Voice", callback_data="nav_voice"),
            InlineKeyboardButton("🕘 History", callback_data="nav_history"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="nav_settings"),
            InlineKeyboardButton("ℹ️ About", callback_data="nav_about"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 **Welcome, {user.first_name}!**\n\n"
        f"I am your **AI Research Assistant** — a high-precision knowledge synthesis and live web intelligence engine.\n\n"
        f"✨ **Core Capabilities:**\n"
        f"• 🔬 **Deep Research**: Autonomous multi-stage web exploration, evidence cross-checking, and citation-grounded reports (`/research <topic>`)\n"
        f"• ⚡ **Quick Answer**: Direct, verified concise summaries (`/quick <topic>`)\n"
        f"• 🎓 **Understand This Topic**: Intuitive tutor guides with metaphors, mechanics, and quizzes\n"
        f"• 🌐 **Multilingual**: English, हिन्दी (Hindi), తెలుగు (Telugu), العربية (Arabic with RTL)\n"
        f"• 🎙️ **Voice Interaction**: Send any voice note to research or chat\n\n"
        f"What would you like to explore today?"
    )

    await safe_send(context, update.effective_chat.id, welcome_text, reply_markup=reply_markup, language=user_lang)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /help command."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    user_lang = db.get_user_setting(user_id, "language", "en")

    help_text = (
        "📖 **ResearchAI Assistant — Command Guide**\n\n"
        "🔍 **Research & Learning:**\n"
        "• `/research <topic>` or `/deep <topic>` — Autonomous multi-source deep research with citations\n"
        "• `/quick <topic>` — Direct, concise synthesized answer\n"
        "• `/sources` — View verified references and evidence from your latest research\n"
        "• `/history` — Browse your previous research dossiers\n\n"
        "🌐 **Customization & Voice:**\n"
        "• `/language` — Switch target language (English, Hindi, Telugu, Arabic)\n"
        "• `/voice` — Configure voice note response preferences\n"
        "• `/clear` — Safely reset and clear your conversation history\n"
        "• `/setkey <key>` — Set personal Google Gemini API key\n"
        "• `/about` — About this AI Assistant\n\n"
        "💡 *Tip: You can also send a voice message or type any question directly!*"
    )
    await safe_send(context, update.effective_chat.id, help_text, language=user_lang)


async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /research or /deep <topic>."""
    if not update.message:
        return
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text(
            "🔬 **Deep Research Mode**\n\nUsage: `/research <topic>`\n"
            "Example: `/research Breakthroughs in CRISPR and base editing 2026`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return
    await execute_research_pipeline(update, context, question=question, mode="deep")


async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /quick <topic>."""
    if not update.message:
        return
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text(
            "⚡ **Quick Answer Mode**\n\nUsage: `/quick <topic>`\n"
            "Example: `/quick How does nuclear fusion produce net energy?`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return
    await execute_research_pipeline(update, context, question=question, mode="simple")


async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /sources command to inspect the latest session's citations."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    session = db.get_latest_research_session(user_id)

    if not session or not session.get("sources"):
        await update.message.reply_text("📚 No recent research sources found. Run `/research <topic>` to explore a topic.")
        return

    sources = session["sources"]
    query = session.get("query", "Latest Topic")
    sources_text = f"📚 **Verified Sources for:** _{query}_\n\n"

    for idx, s in enumerate(sources, 1):
        title = s.get("title", "Untitled Source")
        url = s.get("url", "#")
        domain = s.get("domain", "")
        stype = s.get("source_type", "Web Source")
        why = s.get("why_relevant", "Relevant evidence.")
        sources_text += f"**[{idx}] [{title}]({url})**\n- Domain: `{domain}` | Type: `{stype}`\n- Rationale: _{why}_\n\n"

    chunks = split_message_safely(sources_text)
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=constants.ParseMode.MARKDOWN, disable_web_page_preview=True)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /language command."""
    keyboard = [
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇮🇳 हिन्दी (Hindi)", callback_data="lang_hi"),
        ],
        [
            InlineKeyboardButton("🇮🇳 తెలుగు (Telugu)", callback_data="lang_te"),
            InlineKeyboardButton("🇸🇦 العربية (Arabic)", callback_data="lang_ar"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = "🌐 **Select your preferred research and response language:**"
    if update.message:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /voice preferences."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    voice_enabled = bool(db.get_user_setting(user_id, "voice_enabled", 1))

    status_str = "🟢 Enabled" if voice_enabled else "🔴 Disabled"
    keyboard = [
        [
            InlineKeyboardButton("🔊 Enable Voice Notes", callback_data="voice_on"),
            InlineKeyboardButton("🔇 Disable Voice Notes", callback_data="voice_off"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🎙️ **Voice Processing Settings**\n\n"
        f"• **Current Status:** {status_str}\n"
        f"• **How it works:** When you send an audio voice note, the assistant transcribes your speech in any language, executes the research, and returns a verified answer.",
        reply_markup=reply_markup,
        parse_mode=constants.ParseMode.MARKDOWN,
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /history command to list past dossiers."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    history = db.get_user_research_history(user_id, limit=5)

    if not history:
        await update.message.reply_text("🕘 You have no past research history yet. Submit a topic with `/research` to get started!")
        return

    hist_text = "🕘 **Your Recent Research Dossiers:**\n\n"
    for i, s in enumerate(history, 1):
        q = s.get("query", "Untitled")
        mode = "🔬 Deep" if s.get("mode") == "deep" else "⚡ Quick"
        ts = s.get("created_at", "")[:16]
        src_cnt = len(s.get("sources") or [])
        hist_text += f"**{i}. {q}**\n- Mode: {mode} | Date: `{ts}` | Sources: `{src_cnt}`\n\n"

    await update.message.reply_text(hist_text, parse_mode=constants.ParseMode.MARKDOWN)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /clear command with strict isolation for the requesting user."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    count = db.clear_user_conversation(user_id)
    await update.message.reply_text(
        f"🧹 **Conversation Cleared**: Removed `{count}` recent messages from your session. Your research history remains safely archived.",
        parse_mode=constants.ParseMode.MARKDOWN,
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /about command."""
    about_text = (
        "🤖 **About ResearchAI Assistant**\n\n"
        "• **Identity:** Production AI Research & Knowledge Assistant representing Mohammed Asim (@Asimm07), AI/ML Student.\n"
        "• **Core Engine:** Autonomous multi-stage planner with live DuckDuckGo retrieval and Gemini LLM synthesis.\n"
        "• **Architecture:** Isolated SQLite persistence (WAL mode), per-user rate limiting, multimodal audio transcription, and strict citation grounding.\n"
        "• **Version:** `2.5.0 Production Edition`"
    )
    if update.message:
        await update.message.reply_text(about_text, parse_mode=constants.ParseMode.MARKDOWN)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /admin dashboard with strict authorization."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id

    if not is_authorized_admin(user_id):
        logger.warning(f"Unauthorized /admin access attempt by user {user_id}")
        db.log_event(user_id, "unauthorized_admin_access", f"User {user_id}", status="blocked")
        await update.message.reply_text("⛔ **Access Denied**: This command is restricted to system administrators.")
        return

    metrics = db.get_admin_metrics()
    langs_str = ", ".join(f"{k.upper()}: {v}" for k, v in metrics.get("language_breakdown", {}).items()) or "None"

    admin_dashboard = (
        "📊 **ResearchAI Administrator Dashboard**\n\n"
        f"👥 **User Metrics:**\n"
        f"• Total Registered Users: `{metrics.get('total_users', 0)}`\n"
        f"• Active Users (Last 24h): `{metrics.get('active_users_24h', 0)}`\n\n"
        f"🔬 **Research Telemetry:**\n"
        f"• Total Queries Executed: `{metrics.get('total_queries', 0)}`\n"
        f"• Queries Today: `{metrics.get('queries_today', 0)}`\n"
        f"• Avg Research Duration: `{metrics.get('avg_research_duration_seconds', 0)}s`\n\n"
        f"🌐 **Language Distribution:**\n"
        f"• {langs_str}\n\n"
        f"🛡️ **System Health & Reliability:**\n"
        f"• Total Events: `{metrics.get('total_events', 0)}`\n"
        f"• Error Rate: `{metrics.get('error_rate_pct', 0)}%` (`{metrics.get('error_count', 0)}` errors)\n"
        f"• Database Status: 🟢 Connected (SQLite WAL)\n"
    )

    recent_errs = metrics.get("recent_errors", [])
    if recent_errs:
        admin_dashboard += "\n⚠️ **Recent Failures:**\n"
        for err in recent_errs:
            admin_dashboard += f"- `[{err.get('created_at', '')[:16]}]` {err.get('event_type')}: _{truncate_text(err.get('details', ''), 60)}_\n"

    await update.message.reply_text(admin_dashboard, parse_mode=constants.ParseMode.MARKDOWN)


async def setkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /setkey <api_key>."""
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "🔑 **Set Your Gemini API Key:**\n\n"
            "Usage: `/setkey AIzaSy...`\n\n"
            "Get a free API key at [Google AI Studio](https://aistudio.google.com/app/apikey)",
            parse_mode=constants.ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

    raw_key = args[0].strip()
    if len(raw_key) < 15:
        await update.message.reply_text("❌ Provided key is too short. Please verify your Gemini API key.")
        return

    db.update_user_setting(user_id, "custom_api_key", raw_key)
    try:
        await update.message.delete()
    except Exception:
        pass

    await update.effective_chat.send_message(
        "✅ **Gemini API Key configured successfully!**\nYour key is active and securely isolated to your profile.",
        parse_mode=constants.ParseMode.MARKDOWN,
    )


# ==============================================================================
# Voice & Audio Processing Handler
# ==============================================================================

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming voice notes and audio messages."""
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    voice = update.message.voice or update.message.audio

    if not voice:
        return

    voice_enabled = bool(db.get_user_setting(user_id, "voice_enabled", 1))
    if not voice_enabled:
        await safe_send(context, chat_id, "🔇 Voice processing is currently disabled for your session. Use `/voice` to enable it.")
        return

    api_key = get_effective_user_api_key(user_id)
    if not api_key:
        await safe_send(context, chat_id, "🔑 Please set your Gemini API key using `/setkey <key>` to enable voice transcription.")
        return

    status_msg = await safe_send(context, chat_id, "🎙️ *Listening to your voice note and transcribing...*")

    try:
        file = await context.bot.get_file(voice.file_id)
        audio_buffer = bytearray()
        await file.download_as_bytearray(audio_buffer)

        transcription, detected_lang = await asyncio.to_thread(
            transcribe_voice_message,
            audio_bytes=bytes(audio_buffer),
            mime_type="audio/ogg",
            api_key=api_key,
        )

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        except Exception:
            pass

        if not transcription:
            await safe_send(context, chat_id, "⚠️ Could not clearly transcribe your voice message. Please try speaking closer to the microphone or send a text message.")
            return

        await safe_send(context, chat_id, f"🗣️ **Transcribed ({detected_lang.upper()}):**\n_{transcription}_")

        # Log voice note in contact inbox
        db.log_contact_message(
            user_id=user_id,
            username=update.effective_user.username or "",
            name=f"{update.effective_user.first_name or ''} {update.effective_user.last_name or ''}".strip(),
            message=f"[Voice Note] {transcription}",
        )

        # Alert Admin (Asim)
        if user_id not in default_config.admin_user_ids and default_config.admin_user_ids:
            sender_label = f"@{update.effective_user.username}" if update.effective_user.username else f"{update.effective_user.first_name or 'User'}"
            alert_text = (
                f"🎙️ **New Voice Note in Your Absence**\n"
                f"👤 **From:** {sender_label} (`{user_id}`)\n"
                f"🗣️ **Transcribed:** _{truncate_text(transcription, 300)}_\n\n"
                f"🤖 _Your AI Assistant answered in their language and noted the message._"
            )
            for admin_id in default_config.admin_user_ids:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=alert_text, parse_mode=constants.ParseMode.MARKDOWN)
                except Exception as notify_err:
                    logger.debug(f"Admin notification failed for {admin_id}: {notify_err}")

        # Process transcribed query as a research or chat request
        keyboard = [
            [
                InlineKeyboardButton("🔬 Deep Research", callback_data="act_deep"),
                InlineKeyboardButton("⚡ Quick Answer", callback_data="act_quick"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Store topic in user_data
        if context.user_data is not None:
            context.user_data["pending_topic"] = transcription

        # Auto-answer conversationally or provide action buttons
        user_lang = db.get_user_setting(user_id, "language", detected_lang if detected_lang in SUPPORTED_LANGUAGES else "en")
        ai_reply = await asyncio.to_thread(
            generate_conversational_reply,
            user_id=user_id,
            message=transcription,
            api_key=api_key,
            language=user_lang,
        )
        await safe_send(context, chat_id, ai_reply, reply_markup=reply_markup, language=user_lang)

    except Exception as e:
        logger.exception("Voice processing failed:")
        db.log_event(user_id, "voice_transcription", str(e), status="error")
        await safe_send(context, chat_id, "❌ An error occurred while processing your voice note. Please try again.")


# ==============================================================================
# Text Message & Callback Handlers
# ==============================================================================

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles general text messages."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    if text.startswith("/"):
        return

    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    user_id = user.id
    chat_id = chat.id

    # Log note in contact inbox
    db.log_contact_message(
        user_id=user_id,
        username=user.username or "",
        name=f"{user.first_name or ''} {user.last_name or ''}".strip(),
        message=text,
    )

    # Instant alert to Asim (Admin) when someone texts the bot
    if user_id not in default_config.admin_user_ids and default_config.admin_user_ids:
        sender_label = f"@{user.username}" if user.username else f"{user.first_name or 'User'}"
        alert_text = (
            f"🔔 **New Message in Your Absence**\n"
            f"👤 **From:** {sender_label} (`{user_id}`)\n"
            f"💬 **Message:** _{truncate_text(text, 300)}_\n\n"
            f"🤖 _Your AI Assistant responded in their language and noted the message._"
        )
        for admin_id in default_config.admin_user_ids:
            try:
                await context.bot.send_message(chat_id=admin_id, text=alert_text, parse_mode=constants.ParseMode.MARKDOWN)
            except Exception as notify_err:
                logger.debug(f"Admin notification failed for {admin_id}: {notify_err}")

    if context.user_data is not None:
        context.user_data["pending_topic"] = text

    user_lang = db.get_user_setting(user_id, "language", "en")
    api_key = get_effective_user_api_key(user_id)

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    except Exception:
        pass

    ai_reply = await asyncio.to_thread(
        generate_conversational_reply,
        user_id=user_id,
        message=text,
        api_key=api_key,
        language=user_lang,
    )

    keyboard = [
        [
            InlineKeyboardButton("🔬 Deep Web Research", callback_data="act_deep"),
            InlineKeyboardButton("⚡ Quick Answer", callback_data="act_quick"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await safe_send(context, chat_id, ai_reply, reply_markup=reply_markup, language=user_lang)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all Inline Keyboard button clicks."""
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data
    user_id = update.effective_user.id if update.effective_user else 0

    if data == "nav_research":
        await query.message.reply_text(
            "🔬 **Deep Research Mode**\n\nPlease send your topic like this:\n`/research Your question here`\n\n*Example:* `/research Current state of solid-state batteries`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    elif data == "nav_quick":
        await query.message.reply_text(
            "⚡ **Quick Answer Mode**\n\nPlease send your question like this:\n`/quick Your question here`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    elif data == "nav_sources":
        await sources_command(update, context)
    elif data == "nav_language":
        await language_command(update, context)
    elif data == "nav_voice":
        await voice_command(update, context)
    elif data == "nav_history":
        await history_command(update, context)
    elif data == "nav_about":
        await about_command(update, context)
    elif data == "nav_settings":
        status_txt = (
            "⚙️ **Your Isolated Profile Settings**\n\n"
            f"• **Language:** `{db.get_user_setting(user_id, 'language', 'en').upper()}`\n"
            f"• **Voice Mode:** `{'Enabled' if db.get_user_setting(user_id, 'voice_enabled', 1) else 'Disabled'}`\n"
            f"• **Custom API Key:** `{'Configured' if db.get_user_setting(user_id, 'custom_api_key') else 'Using System Default'}`\n\n"
            "Use `/language`, `/voice`, or `/setkey` to adjust settings."
        )
        await query.message.reply_text(status_txt, parse_mode=constants.ParseMode.MARKDOWN)

    elif data.startswith("lang_"):
        lang_code = data.split("_")[1]
        db.update_user_setting(user_id, "language", lang_code)
        lang_info = SUPPORTED_LANGUAGES.get(lang_code, {"native": lang_code})
        await query.edit_message_text(
            f"✅ **Language configured to {lang_info['native']} ({lang_code.upper()})!**\nAll future research dossiers and responses will be generated in {lang_info['native']}.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    elif data in ("voice_on", "voice_off"):
        enabled = 1 if data == "voice_on" else 0
        db.update_user_setting(user_id, "voice_enabled", enabled)
        state_str = "Enabled 🔊" if enabled else "Disabled 🔇"
        await query.edit_message_text(f"✅ Voice note processing is now **{state_str}**.")

    elif data in ("act_deep", "act_quick"):
        topic = context.user_data.get("pending_topic", "") if context.user_data else ""
        if not topic:
            await query.message.reply_text("⚠️ No active topic found. Please send your question again.")
            return
        mode = "deep" if data == "act_deep" else "simple"
        await execute_research_pipeline(update, context, question=topic, mode=mode)

    elif data.startswith("show_sources_"):
        await sources_command(update, context)

    elif data.startswith("show_teach_"):
        session = db.get_latest_research_session(user_id)
        if session and session.get("teaching_markdown"):
            chunks = split_message_safely(f"🎓 **Pedagogical Tutor Guide**\n\n{session['teaching_markdown']}")
            for chunk in chunks:
                await safe_send(context, query.message.chat_id, chunk, language=session.get("language", "en"))
        else:
            await query.message.reply_text("No tutor guide available for this session.")


# ==============================================================================
# Error Boundary Middleware
# ==============================================================================

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches unhandled exceptions, logs them with structure, and protects user experience."""
    logger.error("Exception while handling Telegram update:", exc_info=context.error)
    user_id = None
    if isinstance(update, Update) and update.effective_user:
        user_id = update.effective_user.id
        db.log_event(user_id, "unhandled_exception", str(context.error), status="error")

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Something went wrong while processing your request. Please try again in a moment.",
            )
        except Exception:
            pass


# ==============================================================================
# Application Factory & Production Entrypoint
# ==============================================================================

def create_production_bot_app(token: Optional[str] = None) -> Application:
    """Builds and wires the production Telegram application with all command and event handlers."""
    bot_token = token or default_config.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured. Please set TELEGRAM_BOT_TOKEN in .env.")

    app = ApplicationBuilder().token(bot_token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler(["research", "deep"], research_command))
    app.add_handler(CommandHandler("quick", quick_command))
    app.add_handler(CommandHandler("sources", sources_command))
    app.add_handler(CommandHandler(["lang", "language"], language_command))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("setkey", setkey_command))

    # Media & Interactive Handlers
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_message_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    # Global Error Boundary
    app.add_error_handler(global_error_handler)

    return app


# Backward compatibility aliases
split_markdown_message = split_message_safely
create_telegram_bot_app = create_production_bot_app
load_user_prefs = lambda: {}
save_user_prefs = lambda _: None


def main():
    """Starts the bot in Webhook mode (if configured) or resilient Polling mode."""
    print("=" * 65)
    print("🤖 ResearchAI Production Telegram Bot Launching...")
    print("=" * 65)

    # Start Observability Health Server on port 8080
    from observability import HealthServer
    health_server = HealthServer(host="0.0.0.0", port=8080)
    health_server.start()

    app = create_production_bot_app()

    webhook_url = default_config.webhook_url
    if webhook_url:
        print(f"🔒 Starting in Webhook Mode on port {default_config.webhook_port}...")
        print(f"🌐 Webhook URL: {webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=default_config.webhook_port,
            url_path="telegram-webhook",
            webhook_url=f"{webhook_url.rstrip('/')}/telegram-webhook",
            secret_token=default_config.webhook_secret_token,
        )
    else:
        print("📡 Starting in Long Polling Mode...")
        app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
