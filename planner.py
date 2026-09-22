"""
planner.py - Research Planning and Query Generation for ResearchAI.
Deconstructs high-level research questions into analytical dimensions
and produces targeted, search-optimized queries.
"""

from dataclasses import dataclass, asdict
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ResearchPlan:
    """Structured breakdown and execution plan for a research topic."""
    core_question: str
    intent_summary: str
    research_dimensions: List[str]
    search_queries: List[str]
    target_evidence_types: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


class ResearchPlanner:
    """
    Formulates research objectives and search strategies using Google Gemini LLM.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def _call_gemini_json(self, prompt: str, system_instruction: str) -> str:
        """Helper to invoke Gemini API and return raw response text."""
        # 1. Try google-genai (new official SDK)
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
            logger.debug(f"google-genai client attempt: {e_new}. Trying google.generativeai fallback.")

        # 2. Fallback to google.generativeai (classic SDK)
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
            logger.error(f"Both Gemini SDK calls failed in ResearchPlanner: {e_classic}")
            raise RuntimeError(f"Failed to communicate with Gemini API: {e_classic}")

        return "{}"

    def plan_research(self, question: str, max_queries: int = 4) -> ResearchPlan:
        """
        Creates a structured research plan and generates optimal search queries.
        """
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("Research question cannot be empty.")

        system_instruction = (
            "You are the Lead Planning Agent for ResearchAI, a high-rigor analytics and scientific research engine. "
            "Your role is to decompose user questions into analytical sub-topics and output concrete, highly specific "
            "search queries that will surface reputable empirical data, benchmarks, authoritative reports, and diverse viewpoints. "
            "Always return strictly valid JSON matching the requested schema."
        )

        prompt = f"""Deconstruct this research question into a comprehensive research plan:
Research Question: "{cleaned_question}"

Generate up to {max_queries} distinct, high-impact web search queries.
Ensure queries cover:
1. Core definition and primary state of the art / current status.
2. Concrete real-world data, case studies, or quantitative benchmarks.
3. Emerging trends, criticisms, limitations, or counterpoints.

Output JSON format:
{{
  "intent_summary": "A 1-2 sentence clarification of what exact insights this research aims to discover.",
  "research_dimensions": [
    "Dimension 1 (e.g. Core Architecture / Methodology)",
    "Dimension 2 (e.g. Industry Applications & Performance)",
    "Dimension 3 (e.g. Tradeoffs & Future Outlook)"
  ],
  "search_queries": [
    "search query 1",
    "search query 2",
    "search query 3"
  ],
  "target_evidence_types": [
    "Peer-reviewed studies or technical whitepapers",
    "Empirical benchmarks and adoption statistics",
    "Case studies and production deployment reports"
  ]
}}
"""

        try:
            raw_json = self._call_gemini_json(prompt, system_instruction)
            # Parse JSON
            # Clean markdown json code blocks if present
            cleaned_json = re.sub(r"^```json\s*", "", raw_json.strip())
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json.strip())
            data = json.loads(cleaned_json)

            intent_summary = data.get("intent_summary") or f"Investigate empirical evidence regarding: {cleaned_question}"
            dimensions = data.get("research_dimensions") or ["Core Concepts", "Current Status", "Key Challenges"]
            queries = data.get("search_queries") or [cleaned_question]
            target_evidence = data.get("target_evidence_types") or ["Articles", "Case Studies", "Technical Analysis"]

            # Cap queries
            queries = [q.strip() for q in queries if q.strip()][:max_queries]
            if not queries:
                queries = [cleaned_question]

            return ResearchPlan(
                core_question=cleaned_question,
                intent_summary=intent_summary,
                research_dimensions=dimensions,
                search_queries=queries,
                target_evidence_types=target_evidence,
            )

        except Exception as exc:
            logger.warning(f"Failed LLM plan generation, using deterministic heuristic plan: {exc}")
            # Robust deterministic fallback
            return ResearchPlan(
                core_question=cleaned_question,
                intent_summary=f"In-depth investigation of '{cleaned_question}'",
                research_dimensions=["Overview & Fundamentals", "Current Trends & Applications", "Key Challenges & Tradeoffs"],
                search_queries=[
                    cleaned_question,
                    f"{cleaned_question} latest trends overview",
                    f"{cleaned_question} challenges tradeoffs analysis",
                ][:max_queries],
                target_evidence_types=["Industry Reports", "Technical Overviews", "Case Studies"],
            )
