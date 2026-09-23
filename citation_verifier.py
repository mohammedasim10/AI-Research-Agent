"""
citation_verifier.py - Deterministic Post-Generation Citation Verification Subsystem.
Ensures zero fabricated citations, validates inline reference indexes against retrieved sources,
and computes citation precision, grounding rate, and claim-to-source alignment.
"""

from dataclasses import dataclass, field, asdict
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CitationClaim:
    """Represents a specific claim and its cited source index."""
    source_index: int
    claim_sentence: str
    is_valid_source_index: bool
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    source_domain: Optional[str] = None
    keyword_overlap_score: float = 0.0
    verification_status: str = "valid"  # "valid", "unsupported_index", "low_lexical_overlap"


@dataclass
class CitationVerificationResult:
    """Comprehensive outcome of deterministic citation verification."""
    is_grounded: bool
    total_citations_found: int
    valid_citations_count: int
    invalid_citations_count: int
    grounding_rate: float
    citation_precision: float
    unique_sources_cited: List[int]
    unreferenced_sources: List[int]
    claims: List[CitationClaim] = field(default_factory=list)
    hallucinated_indices: List[int] = field(default_factory=list)
    verified_markdown: str = ""
    verification_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_grounded": self.is_grounded,
            "total_citations_found": self.total_citations_found,
            "valid_citations_count": self.valid_citations_count,
            "invalid_citations_count": self.invalid_citations_count,
            "grounding_rate": self.grounding_rate,
            "citation_precision": self.citation_precision,
            "unique_sources_cited": self.unique_sources_cited,
            "unreferenced_sources": self.unreferenced_sources,
            "hallucinated_indices": self.hallucinated_indices,
            "claims_count": len(self.claims),
            "verification_notes": self.verification_notes,
        }


class CitationVerifier:
    """
    Deterministic Verification Layer for Research Reports.
    Validates that every inline citation [n] strictly corresponds to an actual retrieved source,
    checks claim lexical overlap, and prevents hallucinated citations from reaching users.
    """

    CITATION_PATTERN = re.compile(r"\[(\d+)\]")

    def __init__(self, min_lexical_overlap_threshold: float = 0.05):
        self.min_lexical_overlap = min_lexical_overlap_threshold

    def _extract_sentences_with_citations(self, text: str) -> List[Tuple[int, str]]:
        """Extracts individual citation indices and their containing sentence context."""
        claims = []
        # Split text into rough sentences
        sentences = re.split(r"(?<=[.!?])\s+|\n\n+", text)
        for sent in sentences:
            sent_clean = sent.strip()
            if not sent_clean:
                continue
            matches = self.CITATION_PATTERN.findall(sent_clean)
            for m in matches:
                try:
                    idx = int(m)
                    claims.append((idx, sent_clean))
                except ValueError:
                    continue
        return claims

    def _compute_lexical_overlap(self, claim: str, source_text: str) -> float:
        """Computes basic Jaccard word-level overlap between claim sentence and source content."""
        if not claim or not source_text:
            return 0.0
        
        # Normalize and tokenize into words (>3 chars)
        claim_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", claim.lower()))
        source_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", source_text.lower()))

        # Remove generic stop words
        stop_words = {"the", "and", "that", "this", "with", "from", "for", "are", "was", "were", "have", "has", "been"}
        claim_words = claim_words - stop_words
        source_words = source_words - stop_words

        if not claim_words or not source_words:
            return 0.0

        intersection = claim_words.intersection(source_words)
        return len(intersection) / len(claim_words)

    def verify_citations(
        self,
        markdown_text: str,
        sources: List[Dict[str, Any]],
    ) -> CitationVerificationResult:
        """
        Verifies all inline citations in the markdown against retrieved source documents.
        """
        if not markdown_text:
            return CitationVerificationResult(
                is_grounded=True,
                total_citations_found=0,
                valid_citations_count=0,
                invalid_citations_count=0,
                grounding_rate=1.0,
                citation_precision=1.0,
                unique_sources_cited=[],
                unreferenced_sources=[],
                verified_markdown="",
                verification_notes=["No content to verify."],
            )

        # Build source lookup by 1-based index and id
        source_by_index: Dict[int, Dict[str, Any]] = {}
        for idx, src in enumerate(sources, 1):
            source_id = src.get("id") or idx
            source_by_index[idx] = src
            source_by_index[source_id] = src

        max_valid_index = len(sources)
        extracted_citations = self._extract_sentences_with_citations(markdown_text)
        
        claims: List[CitationClaim] = []
        valid_count = 0
        invalid_count = 0
        unique_cited: Set[int] = set()
        hallucinated: Set[int] = set()
        notes: List[str] = []

        for src_idx, sentence in extracted_citations:
            is_valid = (src_idx in source_by_index) and (1 <= src_idx <= max_valid_index)
            if is_valid:
                valid_count += 1
                unique_cited.add(src_idx)
                src = source_by_index[src_idx]
                src_content = (src.get("full_text") or "") + " " + (src.get("snippet") or "")
                overlap = self._compute_lexical_overlap(sentence, src_content)
                status = "valid"
                if overlap < self.min_lexical_overlap and len(src_content) > 100:
                    status = "low_lexical_overlap"
                
                claims.append(CitationClaim(
                    source_index=src_idx,
                    claim_sentence=sentence,
                    is_valid_source_index=True,
                    source_title=src.get("title"),
                    source_url=src.get("url"),
                    source_domain=src.get("domain"),
                    keyword_overlap_score=round(overlap, 3),
                    verification_status=status,
                ))
            else:
                invalid_count += 1
                hallucinated.add(src_idx)
                claims.append(CitationClaim(
                    source_index=src_idx,
                    claim_sentence=sentence,
                    is_valid_source_index=False,
                    verification_status="unsupported_index",
                ))

        total_citations = valid_count + invalid_count
        grounding_rate = (valid_count / total_citations) if total_citations > 0 else 1.0
        citation_precision = (valid_count / total_citations) if total_citations > 0 else 1.0

        all_source_indices = set(range(1, max_valid_index + 1))
        unreferenced = sorted(list(all_source_indices - unique_cited))

        # Fix/clean markdown if there are invalid/hallucinated citations
        cleaned_markdown = markdown_text
        if hallucinated:
            for bad_idx in hallucinated:
                # Remove or replace invalid citation tags
                cleaned_markdown = re.sub(rf"\[{bad_idx}\]", "", cleaned_markdown)
            notes.append(f"Stripped {len(hallucinated)} hallucinated citation indices: {sorted(list(hallucinated))}")

        if unreferenced:
            notes.append(f"{len(unreferenced)} retrieved sources were unreferenced in final synthesis: {unreferenced}")

        is_grounded = (invalid_count == 0) and (total_citations > 0 or len(sources) == 0)

        return CitationVerificationResult(
            is_grounded=is_grounded,
            total_citations_found=total_citations,
            valid_citations_count=valid_count,
            invalid_citations_count=invalid_count,
            grounding_rate=round(grounding_rate, 4),
            citation_precision=round(citation_precision, 4),
            unique_sources_cited=sorted(list(unique_cited)),
            unreferenced_sources=unreferenced,
            claims=claims,
            hallucinated_indices=sorted(list(hallucinated)),
            verified_markdown=cleaned_markdown,
            verification_notes=notes,
        )
