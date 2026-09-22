"""
search.py - Modular Search Engine Integration for ResearchAI.
Supports zero-configuration DuckDuckGo web search with retry logic, rate-limit resilience,
URL deduplication, and structured metadata output.
"""

from dataclasses import dataclass, asdict
import logging
import time
import warnings
from typing import List, Optional, Set
from utils.helpers import extract_domain, clean_text

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Standardized structured search result."""
    title: str
    url: str
    snippet: str
    domain: str
    query: str

    def to_dict(self) -> dict:
        return asdict(self)


class SearchClient:
    """
    Modular web search client with DuckDuckGo backend and robust fallback handling.
    """

    def __init__(self, timeout: int = 10, max_results_per_query: int = 3):
        self.timeout = timeout
        self.max_results_per_query = max_results_per_query

    def search_single_query(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """
        Executes a single web search query using DuckDuckGo.
        """
        limit = max_results or self.max_results_per_query
        results: List[SearchResult] = []
        clean_q = query.strip()
        if not clean_q:
            return results

        # 1. Attempt using ddgs / duckduckgo_search DDGS
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS

                with DDGS(timeout=self.timeout) as ddgs:
                    raw_hits = list(ddgs.text(clean_q, max_results=limit))
                    for hit in raw_hits:
                        title = clean_text(hit.get("title", ""))
                        url = hit.get("href") or hit.get("link") or hit.get("url", "")
                        snippet = clean_text(hit.get("body") or hit.get("snippet", ""))
                        
                        if url and (title or snippet):
                            results.append(
                                SearchResult(
                                    title=title or "Untitled Source",
                                    url=url,
                                    snippet=snippet,
                                    domain=extract_domain(url),
                                    query=clean_q,
                                )
                            )
                if results:
                    return results
        except Exception as exc:
            logger.warning(f"DDGS primary search failed for query '{clean_q}': {exc}")

        # 2. Fallback using duckduckgo html endpoint with httpx if primary failed
        try:
            import httpx
            from bs4 import BeautifulSoup

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
            with httpx.Client(timeout=self.timeout, headers=headers, follow_redirects=True) as client:
                resp = client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": clean_q},
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.select(".result__body")
                    for body in links[:limit]:
                        title_elem = body.select_one(".result__title a")
                        snippet_elem = body.select_one(".result__snippet")
                        if title_elem:
                            title = clean_text(title_elem.get_text())
                            raw_href = title_elem.get("href", "")
                            url = raw_href
                            if "uddg=" in raw_href:
                                import urllib.parse
                                match = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query).get("uddg")
                                if match:
                                    url = match[0]
                            snippet = clean_text(snippet_elem.get_text()) if snippet_elem else ""
                            if url.startswith("http"):
                                results.append(
                                    SearchResult(
                                        title=title,
                                        url=url,
                                        snippet=snippet,
                                        domain=extract_domain(url),
                                        query=clean_q,
                                    )
                                )
        except Exception as fallback_exc:
            logger.error(f"Fallback search also failed for '{clean_q}': {fallback_exc}")

        return results

    def search_multiple_queries(
        self,
        queries: List[str],
        max_total_results: int = 8,
    ) -> List[SearchResult]:
        """
        Executes a sequence of queries and returns deduplicated, high-quality search results.
        """
        collected: List[SearchResult] = []
        seen_urls: Set[str] = set()

        for query in queries:
            if len(collected) >= max_total_results:
                break
            try:
                hits = self.search_single_query(query)
                for hit in hits:
                    normalized_url = hit.url.rstrip("/")
                    if normalized_url not in seen_urls:
                        seen_urls.add(normalized_url)
                        collected.append(hit)
                        if len(collected) >= max_total_results:
                            break
                # Gentle throttle between queries to respect provider
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"Error during batch query '{query}': {e}")
                continue

        return collected
