"""
config.py - Centralized Configuration & Environment Validation for ResearchAI.
Ensures secure handling of credentials, zero-leak logging, and modular tunables.
"""

from dataclasses import dataclass, field
import os
from typing import Optional
from dotenv import load_dotenv

# Load local .env file if available
load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration and runtime settings."""
    
    # API Credentials (never logged or hard-coded)
    gemini_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip() or None
    )
    telegram_bot_token: Optional[str] = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    )
    
    # Model Selection
    gemini_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    )
    
    # Web Search & Source Limits
    max_search_queries: int = field(
        default_factory=lambda: int(os.getenv("MAX_SEARCH_QUERIES", "4"))
    )
    max_results_per_query: int = field(
        default_factory=lambda: int(os.getenv("MAX_RESULTS_PER_QUERY", "3"))
    )
    max_total_sources: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOTAL_SOURCES", "8"))
    )
    
    # Network Timeouts (Seconds)
    search_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("SEARCH_TIMEOUT_SECONDS", "10"))
    )
    fetch_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("FETCH_TIMEOUT_SECONDS", "8"))
    )
    
    # Content Constraints
    max_source_content_chars: int = 12000
    snippet_char_limit: int = 400
    
    # Admin Access Control (Comma-separated Telegram user IDs)
    admin_user_ids: tuple = field(
        default_factory=lambda: tuple(
            int(uid.strip())
            for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
            if uid.strip().isdigit()
        )
    )

    # Rate Limiting
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "15"))
    )

    # Webhook Production Settings
    webhook_url: Optional[str] = field(
        default_factory=lambda: os.getenv("WEBHOOK_URL", "").strip() or None
    )
    webhook_secret_token: Optional[str] = field(
        default_factory=lambda: os.getenv("WEBHOOK_SECRET_TOKEN", "").strip() or None
    )
    webhook_port: int = field(
        default_factory=lambda: int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8080")))
    )

    # Environment
    app_env: str = field(
        default_factory=lambda: os.getenv("APP_ENV", "production").strip()
    )
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    )

    def validate_api_key(self, key_override: Optional[str] = None) -> str:
        """
        Validates whether a valid Gemini API key is configured.
        Raises ValueError if missing or invalid without exposing key contents.
        """
        key = (key_override or self.gemini_api_key or "").strip()
        if not key:
            raise ValueError(
                "Gemini API Key is missing. Please provide it in the sidebar or set GEMINI_API_KEY in your .env file."
            )
        if len(key) < 15:
            raise ValueError("Provided Gemini API Key appears invalid (too short).")
        return key


# Global default configuration instance
config = AppConfig()
