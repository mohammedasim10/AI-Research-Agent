"""
rag_engine.py - Retrieval-Augmented Generation (RAG) Context Construction & Ranking Engine.
Handles multi-signal source ranking, domain authority scoring, deduplication,
context budgeting, and optimal context pack generation for LLM synthesis.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from utils.helpers import extract_domain, classify_source_type, clean_text, truncate_text

logger = logging.getLogger(__name__)

DOMAIN_AUTHORITY_WEIGHTS = {
    "Government / Public Health Org": 1.0,
    "Academic / University": 0.95,
    "Scientific Journal / Peer-Reviewed": 0.95,
    "Official Tech Documentation": 0.90,
    "Financial / Regulatory": 0.90,
    "Industry Research / Tech Company": 0.85,
    "News & Analysis": 0.75,
    "General Web Reference": 0.60,
}


@dataclass
class ScoredSource:
    """Represents a source scored by relevance, domain authority, and freshness."""
    source_id: int
    title: str
    url: str
    domain: str
    source_type: str
    snippet: str
    full_text: str
    authority_score: float
    relevance_score: float
    composite_score: float
    key_passages: List[str] = field(default_factory=list)
    raw_source: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "source_type": self.source_type,
            "authority_score": round(self.authority_score, 3),
            "relevance_score": round(self.relevance_score, 3),
            "composite_score": round(self.composite_score, 3),
            "key_passages": self.key_passages,
        }


@dataclass
class RAGContext:
    """Finalized RAG context prepared for LLM ingestion."""
    formatted_context_str: str
    ranked_sources: List[ScoredSource]
    total_tokens_estimated: int
    domains_covered: List[str]
    source_types_represented: List[str]


class RAGEngine:
    """
    RAG Ranking & Context Construction Engine for ResearchAI.
    Ranks sources using authority weights, query alignment, and passage extraction.
    """

    def __init__(self, max_context_chars: int = 24000, max_passages_per_source: int = 3):
        self.max_context_chars = max_context_chars
        self.max_passages_per_source = max_passages_per_source

    def _calculate_relevance(self, query: str, title: str, snippet: str, full_text: str) -> float:
        """Calculates lexical relevance score between research queries and source content."""
        if not query:
            return 0.5

        query_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", query.lower()))
        if not query_tokens:
            return 0.5

        title_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", title.lower()))
        snippet_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", snippet.lower()))
        body_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", full_text[:4000].lower()))

        title_match = len(query_tokens.intersection(title_tokens)) / len(query_tokens)
        snippet_match = len(query_tokens.intersection(snippet_tokens)) / len(query_tokens)
        body_match = len(query_tokens.intersection(body_tokens)) / len(query_tokens)

        # Weighted combination favoring title and snippet density
        score = (title_match * 0.45) + (snippet_match * 0.35) + (body_match * 0.20)
        return min(max(score, 0.1), 1.0)

    def _extract_key_passages(self, text: str, query: str) -> List[str]:
        """Extracts top relevant paragraph chunks from source full text."""
        if not text:
            return []

        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 80]
        if not paragraphs:
            return [truncate_text(text, 400)]

        query_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", query.lower()))
        if not query_tokens:
            return paragraphs[: self.max_passages_per_source]

        scored_paras: List[Tuple[float, str]] = []
        for p in paragraphs:
            p_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", p.lower()))
            overlap = len(query_tokens.intersection(p_tokens))
            scored_paras.append((overlap, p))

        # Sort paragraphs by token overlap descending
        scored_paras.sort(key=lambda x: x[0], reverse=True)
        return [p[1] for p in scored_paras[: self.max_passages_per_source]]

    def rank_and_score_sources(
        self,
        question: str,
        sources: List[Dict[str, Any]],
        search_queries: Optional[List[str]] = None,
    ) -> List[ScoredSource]:
        """Ranks all retrieved sources by composite score (Domain Authority + Relevance)."""
        combined_query = question + " " + " ".join(search_queries or [])
        scored_list: List[ScoredSource] = []

        seen_urls = set()

        for idx, src in enumerate(sources, 1):
            url = src.get("url", "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            title = src.get("title") or "Untitled Source"
            domain = src.get("domain") or extract_domain(url)
            stype = src.get("source_type") or classify_source_type(domain, url, title)
            snippet = src.get("snippet") or ""
            full_text = src.get("full_text") or snippet

            auth_score = DOMAIN_AUTHORITY_WEIGHTS.get(stype, 0.60)
            rel_score = self._calculate_relevance(combined_query, title, snippet, full_text)

            # Composite: 55% relevance, 45% authority
            composite = (rel_score * 0.55) + (auth_score * 0.45)
            passages = self._extract_key_passages(full_text, question)

            scored = ScoredSource(
                source_id=src.get("id") or idx,
                title=title,
                url=url,
                domain=domain,
                source_type=stype,
                snippet=snippet,
                full_text=full_text,
                authority_score=auth_score,
                relevance_score=rel_score,
                composite_score=composite,
                key_passages=passages,
                raw_source=src,
            )
            scored_list.append(scored)

        # Sort descending by composite score
        scored_list.sort(key=lambda s: s.composite_score, reverse=True)
        return scored_list

    def construct_rag_context(
        self,
        question: str,
        sources: List[Dict[str, Any]],
        search_queries: Optional[List[str]] = None,
    ) -> RAGContext:
        """
        Builds a structured RAG context prompt string within strict character/token budget.
        """
        ranked = self.rank_and_score_sources(question, sources, search_queries)
        
        context_blocks: List[str] = []
        current_chars = 0
        domains = set()
        types = set()

        for idx, s in enumerate(ranked, 1):
            domains.add(s.domain)
            types.add(s.source_type)

            passages_text = "\n".join(f"> {p}" for p in s.key_passages) if s.key_passages else f"> {s.snippet}"
            
            block = (
                f"### [SOURCE {idx}]: {s.title}\n"
                f"- **URL:** {s.url}\n"
                f"- **Domain:** {s.domain} | **Source Category:** {s.source_type} (Auth: {s.authority_score:.2f})\n"
                f"- **Verified Content & Key Evidence Passages:**\n"
                f"{passages_text}\n"
            )

            if current_chars + len(block) > self.max_context_chars and context_blocks:
                logger.debug(f"RAG context budget reached ({current_chars} chars). Truncating at {idx-1} sources.")
                break

            context_blocks.append(block)
            current_chars += len(block)

        formatted_context = "\n".join(context_blocks)
        # Approximate tokens ~ 4 chars per token
        est_tokens = max(1, current_chars // 4)

        return RAGContext(
            formatted_context_str=formatted_context,
            ranked_sources=ranked,
            total_tokens_estimated=est_tokens,
            domains_covered=sorted(list(domains)),
            source_types_represented=sorted(list(types)),
        )
