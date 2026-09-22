"""
source_processor.py - Web Content Extractor and Source Normalizer for ResearchAI.
Extracts clean, readable body text from retrieved web pages with strict timeouts,
rate limits, and fallback extraction mechanisms.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
import logging
from typing import Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
from utils.helpers import clean_text, extract_domain, truncate_text

logger = logging.getLogger(__name__)


@dataclass
class ProcessedSource:
    """Represents an enriched, extracted web source."""
    id: int
    title: str
    url: str
    domain: str
    snippet: str
    full_text: str
    word_count: int
    status: str  # "success", "partial", "failed"
    query_origin: str
    why_relevant: Optional[str] = None
    extracted_facts: Optional[List[str]] = None

    def to_dict(self) -> dict:
        return asdict(self)


class SourceProcessor:
    """
    Downloads and extracts high-quality article content from URLs in parallel.
    """

    def __init__(self, timeout: int = 8, max_chars: int = 12000):
        self.timeout = timeout
        self.max_chars = max_chars
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 (ResearchAI Agent)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _extract_with_trafilatura(self, html_content: str) -> Optional[str]:
        """Attempts high-precision text extraction via trafilatura."""
        try:
            import trafilatura
            extracted = trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            return extracted
        except Exception:
            return None

    def _extract_with_bs4(self, html_content: str) -> str:
        """Fallback HTML text extraction using BeautifulSoup."""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            # Strip script, style, nav, footer, header tags
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "aside"]):
                tag.decompose()
            
            # Extract paragraphs and headers
            paragraphs = []
            for elem in soup.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
                txt = clean_text(elem.get_text())
                if len(txt) > 20:
                    paragraphs.append(txt)
            return "\n\n".join(paragraphs)
        except Exception:
            return ""

    def fetch_and_process_url(self, item: dict, source_id: int) -> ProcessedSource:
        """
        Fetches a single URL and extracts clean markdown/text.
        """
        url = item.get("url", "")
        title = item.get("title") or "Untitled Source"
        snippet = item.get("snippet") or ""
        query_origin = item.get("query") or ""
        domain = item.get("domain") or extract_domain(url)

        if not url or not url.startswith("http"):
            return ProcessedSource(
                id=source_id,
                title=title,
                url=url,
                domain=domain,
                snippet=snippet,
                full_text=snippet,
                word_count=len(snippet.split()),
                status="partial",
                query_origin=query_origin,
            )

        extracted_text = ""
        status = "failed"

        try:
            with httpx.Client(
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=True,
                verify=False,  # Resilient to misconfigured SSL certificates on legacy research sites
            ) as client:
                response = client.get(url)
                if response.status_code == 200:
                    html = response.text
                    # 1. Try Trafilatura
                    extracted_text = self._extract_with_trafilatura(html) or ""
                    # 2. Fallback to BeautifulSoup if Trafilatura gave very little
                    if len(extracted_text.strip()) < 150:
                        bs4_text = self._extract_with_bs4(html)
                        if len(bs4_text) > len(extracted_text):
                            extracted_text = bs4_text

                    if len(extracted_text.strip()) > 100:
                        status = "success"
                    else:
                        extracted_text = snippet
                        status = "partial"
                else:
                    extracted_text = snippet
                    status = "partial"
        except Exception as exc:
            logger.debug(f"Failed to fetch content from {url}: {exc}")
            extracted_text = snippet
            status = "partial" if snippet else "failed"

        # Sanitize and truncate to character limit
        sanitized_text = clean_text(extracted_text)
        if len(sanitized_text) > self.max_chars:
            sanitized_text = sanitized_text[: self.max_chars] + "\n...[Content truncated for length]"

        word_count = len(sanitized_text.split())

        return ProcessedSource(
            id=source_id,
            title=title,
            url=url,
            domain=domain,
            snippet=snippet,
            full_text=sanitized_text,
            word_count=word_count,
            status=status,
            query_origin=query_origin,
        )

    def process_sources_concurrently(
        self,
        search_results: List[dict],
        max_workers: int = 5,
    ) -> List[ProcessedSource]:
        """
        Processes a list of search hits concurrently.
        """
        results: List[ProcessedSource] = []
        if not search_results:
            return results

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.fetch_and_process_url, hit, idx + 1): idx + 1
                for idx, hit in enumerate(search_results)
            }
            for future in as_completed(future_to_idx):
                try:
                    processed = future.result()
                    results.append(processed)
                except Exception as e:
                    logger.error(f"Worker exception processing source: {e}")

        # Preserve original ranking order by ID
        results.sort(key=lambda s: s.id)
        return results
