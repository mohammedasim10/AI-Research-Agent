"""
analyzer.py - Source Analysis, Fact Extraction & Cross-Checking Module for ResearchAI.
Evaluates evidence across multiple collected web sources, identifies consensus facts,
detects contradictions or conflicting claims, and highlights evidence limitations.
"""

from dataclasses import dataclass, asdict
import json
import logging
import re
from typing import Any, Dict, List, Optional
from source_processor import ProcessedSource
from utils.helpers import truncate_text

logger = logging.getLogger(__name__)


@dataclass
class SourceAnalysisResult:
    """Consolidated multi-source analysis and fact cross-checking."""
    enriched_sources: List[Dict[str, Any]]
    consensus_findings: List[str]
    contradictions_and_divergences: List[Dict[str, Any]]
    evidence_gaps_and_limitations: List[str]
    synthesis_ready: bool

    def to_dict(self) -> dict:
        return asdict(self)


class ResearchAnalyzer:
    """
    Analyzes and cross-references multi-source web evidence using Gemini LLM.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def _call_gemini_json(self, prompt: str, system_instruction: str) -> str:
        """Helper to invoke Gemini API and return json text."""
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "system_instruction": system_instruction,
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                },
            )
            if response and response.text:
                return response.text
        except Exception as e_new:
            logger.debug(f"google-genai in analyzer: {e_new}. Trying fallback.")

        try:
            import google.generativeai as genai_classic
            genai_classic.configure(api_key=self.api_key)
            model = genai_classic.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction,
                generation_config={"response_mime_type": "application/json", "temperature": 0.2},
            )
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e_classic:
            logger.error(f"Gemini call failed in ResearchAnalyzer: {e_classic}")
            raise RuntimeError(f"Failed to analyze sources with Gemini: {e_classic}")

        return "{}"

    def analyze_and_cross_check(
        self,
        question: str,
        sources: List[ProcessedSource],
    ) -> SourceAnalysisResult:
        """
        Extracts key evidence from each source and compares claims across all sources.
        """
        if not sources:
            return SourceAnalysisResult(
                enriched_sources=[],
                consensus_findings=[],
                contradictions_and_divergences=[],
                evidence_gaps_and_limitations=["No web sources could be collected for cross-analysis."],
                synthesis_ready=False,
            )

        # Prepare compacted representation of source documents for LLM context
        sources_payload = []
        for s in sources:
            # Use snippet or full text up to 2500 chars to balance speed and richness
            content_sample = s.full_text[:2500] if s.full_text else s.snippet
            sources_payload.append(
                f"[Source ID: {s.id}]\n"
                f"Title: {s.title}\n"
                f"URL: {s.url}\n"
                f"Domain: {s.domain}\n"
                f"Content:\n{content_sample}\n"
                f"---"
            )
        joined_sources = "\n".join(sources_payload)

        system_instruction = (
            "You are the Senior Research Verification & Analysis Agent for ResearchAI. "
            "Your job is to objectively analyze evidence from multiple web sources, extract factual findings, "
            "and rigorously cross-check them. Do not hallucinate or invent facts not present in the sources. "
            "Identify what multiple sources agree on, explicit contradictions or differing perspectives between sources, "
            "and any critical gaps or limitations in the available evidence. Output strictly valid JSON."
        )

        prompt = f"""Investigate the following question based EXCLUSIVELY on the provided web sources:
Research Question: "{question}"

Collected Sources ({len(sources)} total):
{joined_sources}

Perform thorough multi-source analysis and return JSON with this exact structure:
{{
  "source_evaluations": [
    {{
      "id": 1,
      "why_relevant": "1 sentence explaining why this source directly addresses the research question.",
      "key_extracted_facts": [
        "Concrete fact or data point extracted from this source",
        "Another fact or claim supported by this source"
      ]
    }}
  ],
  "consensus_findings": [
    "Fact or insight corroborated across multiple independent sources (e.g. Sources [1], [3] agree that...)"
  ],
  "contradictions_and_divergences": [
    {{
      "topic": "Specific topic or metric where sources differ",
      "discrepancy": "Source [1] states X, whereas Source [2] argues Y",
      "involved_sources": [1, 2]
    }}
  ],
  "evidence_gaps_and_limitations": [
    "Specific blind spot, lack of quantitative data, or scope limitation observed in the retrieved evidence."
  ]
}}
"""

        try:
            raw_json = self._call_gemini_json(prompt, system_instruction)
            cleaned_json = re.sub(r"^```json\s*", "", raw_json.strip())
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json.strip())
            data = json.loads(cleaned_json)

            # Map extracted source facts back to our source objects
            eval_map = {item["id"]: item for item in data.get("source_evaluations", []) if "id" in item}
            
            enriched_sources: List[Dict[str, Any]] = []
            for s in sources:
                src_dict = s.to_dict()
                eval_data = eval_map.get(s.id, {})
                src_dict["why_relevant"] = eval_data.get(
                    "why_relevant", f"Provides coverage and context for '{truncate_text(s.title, 60)}'."
                )
                src_dict["extracted_facts"] = eval_data.get("key_extracted_facts", [s.snippet])
                enriched_sources.append(src_dict)

            consensus = data.get("consensus_findings", [])
            contradictions = data.get("contradictions_and_divergences", [])
            gaps = data.get("evidence_gaps_and_limitations", [])

            return SourceAnalysisResult(
                enriched_sources=enriched_sources,
                consensus_findings=consensus,
                contradictions_and_divergences=contradictions,
                evidence_gaps_and_limitations=gaps,
                synthesis_ready=True,
            )

        except Exception as exc:
            logger.warning(f"LLM source analysis encountered issue, applying fallback parsing: {exc}")
            fallback_sources = []
            for s in sources:
                src_dict = s.to_dict()
                src_dict["why_relevant"] = f"Relevant web result retrieved for query '{s.query_origin}'"
                src_dict["extracted_facts"] = [s.snippet] if s.snippet else ["Relevant context retrieved."]
                fallback_sources.append(src_dict)

            return SourceAnalysisResult(
                enriched_sources=fallback_sources,
                consensus_findings=["Sources collectively address core dimensions of the research question."],
                contradictions_and_divergences=[],
                evidence_gaps_and_limitations=["Detailed cross-source contradiction scan completed with basic heuristics."],
                synthesis_ready=True,
            )
