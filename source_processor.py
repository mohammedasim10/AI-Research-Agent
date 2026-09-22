"""
source_processor.py - Web Content Extractor and Source Normalizer for ResearchAI.
Extracts clean, readable body text from retrieved web pages with strict timeouts,
source type categorization, publication date extraction, and raw evidence preservation.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import logging
import re
from typing import Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
from utils.helpers import clean_text, extract_domain, classify_source_type, truncate_text

logger = logging.getLogger(__name__)


@dataclass
class ProcessedSource:
    """Represents an enriched, categorized web source with extracted evidence."""
    id: int
    title: str
    url: str
    domain: str
    source_type: str
    snippet: str
    full_text: str
    word_count: int
    status: str  # "success", "partial", "failed"
    query_origin: str
    publication_date: Optional[str] = None
    retrieved_date: str = ""
    why_relevant: Optional[str] = None
    extracted_facts: Optional[List[str]] = None
    direct_evidence_quotes: Optional[List[str]] = None

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
                "Chrome/124.0.0.0 Safari/537.36 (ResearchAI Academic Agent)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _extract_date_from_html(self, soup: BeautifulSoup, raw_html: str) -> Optional[str]:
        """Extracts publication date from meta tags or time elements."""
        try:
            # 1. Meta property inspection
            date_meta_names = [
                "article:published_time",
                "og:published_time",
                "datePublished",
                "date",
                "DC.date.issued",
                "pubdate",
            ]
            for name in date_meta_names:
                meta = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
                if meta and meta.get("content"):
                    val = meta["content"][:10]
                    if re.match(r"^\d{4}-\d{2}-\d{2}", val):
                        return val

            # 2. Time element
            time_tag = soup.find("time")
            if time_tag:
                dt = time_tag.get("datetime") or time_tag.get_text()
                if dt:
                    match = re.search(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", dt)
                    if match:
                        return match.group(1).replace("/", "-").replace(".", "-")
        except Exception:
            pass
        return None

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
            
            paragraphs = []
            for elem in soup.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
                txt = clean_text(elem.get_text())
                if len(txt) > 25:
                    paragraphs.append(txt)
            return "\n\n".join(paragraphs)
        except Exception:
            return ""

    def fetch_and_process_url(self, item: dict, source_id: int) -> ProcessedSource:
        """
        Fetches a single URL, classifies source type, extracts dates and body text.
        """
        url = item.get("url", "")
        title = item.get("title") or "Untitled Source"
        snippet = item.get("snippet") or ""
        query_origin = item.get("query") or ""
        domain = item.get("domain") or extract_domain(url)
        source_type = classify_source_type(domain, url, title)
        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not url or not url.startswith("http"):
            return ProcessedSource(
                id=source_id,
                title=title,
                url=url,
                domain=domain,
                source_type=source_type,
                snippet=snippet,
                full_text=snippet,
                word_count=len(snippet.split()),
                status="partial",
                query_origin=query_origin,
                retrieved_date=today_date,
            )

        extracted_text = ""
        pub_date = None
        status = "failed"

        try:
            with httpx.Client(
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=True,
                verify=False,
            ) as client:
                response = client.get(url)
                if response.status_code == 200:
                    html = response.text
                    soup = BeautifulSoup(html, "html.parser")
                    pub_date = self._extract_date_from_html(soup, html)
                    
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

        # Extract direct evidence snippet quotes
        direct_quotes = []
        if snippet:
            direct_quotes.append(snippet)
        if sanitized_text and len(sanitized_text) > 100:
            sample_para = [p for p in sanitized_text.split("\n\n") if len(p) > 60]
            if sample_para:
                direct_quotes.append(truncate_text(sample_para[0], 250))

        return ProcessedSource(
            id=source_id,
            title=title,
            url=url,
            domain=domain,
            source_type=source_type,
            snippet=snippet,
            full_text=sanitized_text,
            word_count=word_count,
            status=status,
            query_origin=query_origin,
            publication_date=pub_date,
            retrieved_date=today_date,
            direct_evidence_quotes=direct_quotes[:2],
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
