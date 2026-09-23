"""
tools/scraper.py - Secure Web Content Scraper Tool with SSRF Defense.
"""

from typing import Any, Dict, Optional
from source_processor import SourceProcessor, ProcessedSource
from tools.base import BaseTool, ToolParameter
from utils.security import validate_url_for_ssrf


class ScraperTool(BaseTool):
    """Fetches and extracts readable text from public web URLs with SSRF validation."""

    def __init__(self, source_processor: Optional[SourceProcessor] = None, timeout: int = 8):
        super().__init__(
            name="content_scraper",
            description="Fetches, parses, and extracts readable text and metadata from a public web URL. Protects against SSRF attacks.",
            parameters=[
                ToolParameter(
                    name="url",
                    type_name="string",
                    description="The public web URL to extract content from.",
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type_name="string",
                    description="Optional title or context for the URL.",
                    required=False,
                    default="",
                ),
            ],
        )
        self.source_processor = source_processor or SourceProcessor(timeout=timeout)

    def _run(self, url: str, title: str = "") -> Dict[str, Any]:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("URL cannot be empty")

        # SSRF Defense Check
        is_safe, reason = validate_url_for_ssrf(clean_url, resolve_dns=True)
        if not is_safe:
            raise ValueError(f"Security Alert: URL failed SSRF validation: {reason}")

        item = {"url": clean_url, "title": title}
        processed: ProcessedSource = self.source_processor.fetch_and_process_url(item, source_id=1)
        return processed.to_dict()
