"""
planner.py - Domain-Aware Research Planning & Search Query Formulation for ResearchAI.
Deconstructs high-level research questions into analytical dimensions, detects specific domains
(Healthcare, Technology, Science/Climate, Finance), and produces targeted, diverse search queries.
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
    research_target: str
    intent_summary: str
    detected_domain: str
    research_dimensions: List[str]
    search_queries: List[str]
    target_evidence_types: List[str]
    is_recency_sensitive: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class ResearchPlanner:
    """
    Formulates domain-aware research objectives and search strategies using Gemini LLM.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def _call_gemini_json(self, prompt: str, system_instruction: str) -> str:
        """Helper to invoke Gemini API and return raw response text."""
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
            logger.debug(f"google-genai client attempt in planner: {e_new}. Trying fallback.")

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

    def _detect_domain_heuristics(self, question: str) -> str:
        """Heuristic domain classifier fallback."""
        q_lower = question.lower()
        if any(w in q_lower for w in ["health", "medical", "hospital", "patient", "clinical", "cancer", "disease", "drug", "surgery", "doctor", "medicine", "biotech"]):
            return "Healthcare & Medicine"
        if any(w in q_lower for w in ["climate", "carbon", "warming", "environment", "renewable", "energy", "emission", "biodiversity", "solar", "ecology"]):
            return "Climate & Environment"
        if any(w in q_lower for w in ["finance", "economy", "market", "banking", "gdp", "inflation", "stock", "crypto", "trade"]):
            return "Finance & Economics"
        if any(w in q_lower for w in ["ai", "machine learning", "rag", "software", "python", "algorithm", "llm", "agent", "cloud", "code", "neural", "database"]):
            return "Technology & Computer Science"
        return "General Science & Society"

    def plan_research(self, question: str, max_queries: int = 4) -> ResearchPlan:
        """
        Creates a domain-grounded research plan and generates optimal search queries.
        Ensures that domain questions (e.g. healthcare, climate, finance) target authoritative
        institutions, journals, and official repositories rather than generic company landing pages.
        """
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("Research question cannot be empty.")

        # Check recency sensitivity
        recency_keywords = ["latest", "recent", "today", "current", "2026", "2025", "this year", "breakthroughs", "trends", "new"]
        is_recency = any(k in cleaned_question.lower() for k in recency_keywords)

        system_instruction = (
            "You are the Principal Research Strategist for ResearchAI. "
            "Your role is to deeply analyze the user's research topic, identify the specific domain "
            "(e.g. Healthcare/Medicine, Climate/Environment, Technology/AI, Finance/Economics), and generate "
            "laser-focused search queries that will surface reputable, diverse, authoritative evidence. "
            "CRITICAL SEARCH QUALITY RULES:\n"
            "1. For domain-specific topics (e.g. Healthcare, Medicine, Biology), do NOT return generic AI company homepages. "
            "Formulate search queries that retrieve medical journals, government health agencies (WHO, NIH, CDC, FDA), "
            "clinical trials, and peer-reviewed studies.\n"
            "2. For Technology topics, target official technical documentation, arXiv papers, standards, and research blogs.\n"
            "3. For Climate/Science topics, target scientific agencies (NASA, NOAA, IPCC, Nature, Science).\n"
            "4. Diversify queries across multiple analytical angles (Methodology, Empirical Benchmarks/Data, Criticisms/Challenges).\n"
            "Always return strictly valid JSON."
        )

        prompt = f"""Deconstruct this research question into a domain-aware research strategy:
RESEARCH QUESTION: "{cleaned_question}"
RECENCY SENSITIVE: {is_recency}

Generate up to {max_queries} distinct, high-precision search queries.
Ensure queries span diverse source categories (e.g. academic/peer-reviewed, official government/institutional data, real-world case studies).

Return strictly JSON matching this structure:
{{
  "detected_domain": "Healthcare & Medicine | Technology & AI | Climate & Science | Finance & Economics | General",
  "intent_summary": "1-2 sentence clarification of the core research objective.",
  "research_dimensions": [
    "Dimension 1 (e.g. Clinical Applications in Diagnosis & Imaging)",
    "Dimension 2 (e.g. Empirical Outcomes & Accuracy Benchmarks)",
    "Dimension 3 (e.g. Ethical, Regulatory & Deployment Challenges)"
  ],
  "search_queries": [
    "search query 1 (e.g. AI in clinical healthcare diagnosis NIH WHO peer-reviewed study)",
    "search query 2 (e.g. machine learning medical imaging accuracy clinical trials data)",
    "search query 3 (e.g. AI healthcare adoption challenges regulatory FDA limitations)"
  ],
  "target_evidence_types": [
    "Peer-reviewed medical journals and clinical trials",
    "Government health agency reports (WHO, NIH, FDA)",
    "Hospital deployment case studies and empirical statistics"
  ]
}}
"""

        try:
            raw_json = self._call_gemini_json(prompt, system_instruction)
            cleaned_json = re.sub(r"^```json\s*", "", raw_json.strip())
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json.strip())
            data = json.loads(cleaned_json)

            domain = data.get("detected_domain") or self._detect_domain_heuristics(cleaned_question)
            target = data.get("research_target") or cleaned_question
            intent = data.get("intent_summary") or f"Investigate empirical evidence regarding: {cleaned_question}"
            dimensions = data.get("research_dimensions") or ["Core Concepts", "Current Status", "Key Challenges"]
            queries = data.get("search_queries") or [cleaned_question]
            target_evidence = data.get("target_evidence_types") or ["Articles", "Case Studies", "Technical Analysis"]

            # Filter & clean queries - ensure the research target or a direct synonym is in every query
            clean_queries = [q.strip() for q in queries if q.strip()][:max_queries]
            if not clean_queries:
                clean_queries = [cleaned_question]

            return ResearchPlan(
                core_question=cleaned_question,
                research_target=target,
                intent_summary=intent,
                detected_domain=domain,
                research_dimensions=dimensions,
                search_queries=clean_queries,
                target_evidence_types=target_evidence,
                is_recency_sensitive=is_recency,
            )

        except Exception as exc:
            logger.warning(f"Failed LLM plan generation, using domain heuristic plan: {exc}")
            domain = self._detect_domain_heuristics(cleaned_question)
            
            # Domain-targeted fallback queries
            if "Healthcare" in domain:
                fallback_queries = [
                    f"{cleaned_question} medical research journal",
                    f"{cleaned_question} clinical outcomes NIH WHO",
                    f"{cleaned_question} hospital deployment challenges",
                ]
            elif "Climate" in domain:
                fallback_queries = [
                    f"{cleaned_question} IPCC scientific consensus",
                    f"{cleaned_question} emissions data NOAA NASA",
                    f"{cleaned_question} global policy impact",
                ]
            elif "Finance" in domain:
                fallback_queries = [
                    f"{cleaned_question} economic data central bank",
                    f"{cleaned_question} regulatory analysis report",
                    f"{cleaned_question} market impact research",
                ]
            else:
                fallback_queries = [
                    cleaned_question,
                    f"{cleaned_question} research overview",
                    f"{cleaned_question} empirical benchmarks challenges",
                ]

            return ResearchPlan(
                core_question=cleaned_question,
                research_target=cleaned_question,
                intent_summary=f"In-depth investigation of '{cleaned_question}'",
                detected_domain=domain,
                research_dimensions=["Overview & Fundamentals", "Current Trends & Applications", "Key Challenges & Tradeoffs"],
                search_queries=fallback_queries[:max_queries],
                target_evidence_types=["Institutional Reports", "Technical Overviews", "Case Studies"],
                is_recency_sensitive=is_recency,
            )
