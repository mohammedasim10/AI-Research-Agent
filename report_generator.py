"""
report_generator.py - Academic and Enterprise Research Report Synthesis for ResearchAI.
Produces structured, citation-grounded research reports formatted in Markdown.
"""

from dataclasses import dataclass
import logging
import re
from typing import Any, Dict, List, Optional
from analyzer import SourceAnalysisResult
from planner import ResearchPlan

logger = logging.getLogger(__name__)


@dataclass
class GeneratedReport:
    """The finalized research report containing structured markdown content."""
    markdown_content: str
    citation_count: int
    sections: List[str]


class ResearchReportGenerator:
    """
    Generates structured, highly readable research reports using Gemini LLM.
    Enforces strict citation grounding and transparent separation of facts vs synthesis.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def _call_gemini_text(self, prompt: str, system_instruction: str) -> str:
        """Invokes Gemini API and returns generated markdown text."""
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "system_instruction": system_instruction,
                    "temperature": 0.25,
                },
            )
            if response and response.text:
                return response.text
        except Exception as e_new:
            logger.debug(f"google-genai in report_generator: {e_new}. Trying fallback.")

        try:
            import google.generativeai as genai_classic
            genai_classic.configure(api_key=self.api_key)
            model = genai_classic.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction,
                generation_config={"temperature": 0.25},
            )
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e_classic:
            logger.error(f"Gemini call failed in ResearchReportGenerator: {e_classic}")
            raise RuntimeError(f"Failed to generate report with Gemini: {e_classic}")

        return "Report generation produced empty content."

    def generate_report(
        self,
        question: str,
        plan: ResearchPlan,
        analysis_result: SourceAnalysisResult,
    ) -> GeneratedReport:
        """
        Compiles the analyzed evidence into a cohesive, publication-quality report.
        """
        sources = analysis_result.enriched_sources

        # Format source context with clear IDs for strict citation mapping
        sources_context = []
        for src in sources:
            src_id = src.get("id", 1)
            title = src.get("title", "Untitled")
            domain = src.get("domain", "")
            url = src.get("url", "")
            facts = "\n  - ".join(src.get("extracted_facts", [src.get("snippet", "")]))
            sources_context.append(
                f"[Source {src_id}]\n"
                f"Title: {title}\n"
                f"Domain: {domain}\n"
                f"URL: {url}\n"
                f"Extracted Evidence:\n  - {facts}\n"
            )
        formatted_sources_block = "\n".join(sources_context)

        consensus_block = "\n- ".join(analysis_result.consensus_findings) if analysis_result.consensus_findings else "None identified."
        contradictions_block = ""
        if analysis_result.contradictions_and_divergences:
            for item in analysis_result.contradictions_and_divergences:
                contradictions_block += f"- **{item.get('topic', 'Discrepancy')}**: {item.get('discrepancy', '')} (Sources: {item.get('involved_sources', [])})\n"
        else:
            contradictions_block = "- No significant factual contradictions detected across the analyzed sources.\n"

        gaps_block = "\n- ".join(analysis_result.evidence_gaps_and_limitations) if analysis_result.evidence_gaps_and_limitations else "None specified."

        system_instruction = (
            "You are the Principal Research Synthesizer for ResearchAI, a high-trust enterprise analytics research engine. "
            "Write an exhaustive, objective, professional research report addressing the user's question. "
            "STRICT CITATION RULES:\n"
            "1. You MUST cite sources using bracketed numbers like [1], [2], [1, 3] for every factual statement, statistic, or claim.\n"
            "2. ONLY cite source IDs that actually exist in the provided sources list (e.g. if there are 5 sources, valid citations are [1] to [5]).\n"
            "3. Never fabricate facts, benchmarks, or citations.\n"
            "4. Clearly distinguish empirically sourced facts (cited) from logical analytical synthesis.\n"
            "5. If sources disagree or have conflicting numbers, explicitly describe the divergence."
        )

        prompt = f"""Generate a comprehensive, publication-quality research report for this investigation:

RESEARCH QUESTION:
"{question}"

RESEARCH PLAN OBJECTIVES:
- Intent: {plan.intent_summary}
- Target Dimensions: {', '.join(plan.research_dimensions)}

VERIFIED EVIDENCE & SOURCES:
{formatted_sources_block}

CROSS-SOURCE ANALYSIS SUMMARY:
Consensus Findings:
- {consensus_block}

Contradictions & Discrepancies:
{contradictions_block}

Identified Evidence Limitations & Gaps:
- {gaps_block}

STRUCTURE THE REPORT WITH EXACTLY THESE HEADINGS (using standard Markdown # and ##):

## 1. Executive Summary
A crisp, 2-3 paragraph synthesis answering the core research question directly. Cite primary evidence with [1], [2].

## 2. Key Findings
A clear list of 4-6 bulleted, high-impact takeaways with inline citations [1], [2] and bold lead-ins.

## 3. Detailed Analysis
Thorough multi-paragraph analytical breakdown covering the research dimensions. Organize with clear sub-headings (###) where appropriate. Every paragraph must integrate relevant citations.

## 4. Empirical Evidence & Supporting Data
A structured overview of specific metrics, case studies, benchmarks, and data points surfaced in the evidence.

## 5. Multi-Source Comparison & Discrepancies
An explicit comparison of perspectives across the collected sources. Highlight areas where sources agree strongly and where they differ or offer competing viewpoints.

## 6. Limitations & Evidence Gaps
Critical evaluation of the limitations of the current evidence base (e.g., sample sizes, recency, commercial bias, unverified claims).

## 7. Conclusion & Strategic Outlook
A balanced, forward-looking summary synthesizing the findings.

(Do NOT generate the final Sources / References list in your response, as the application automatically attaches the verified interactive reference cards).
"""

        try:
            markdown = self._call_gemini_text(prompt, system_instruction)
            
            # Count citations [1], [2]
            citations = re.findall(r"\[\d+\]", markdown)
            
            sections = [
                "Executive Summary",
                "Key Findings",
                "Detailed Analysis",
                "Empirical Evidence",
                "Multi-Source Comparison",
                "Limitations",
                "Conclusion",
            ]

            return GeneratedReport(
                markdown_content=markdown.strip(),
                citation_count=len(citations),
                sections=sections,
            )

        except Exception as exc:
            logger.error(f"Error during report generation: {exc}")
            # Resilient fallback markdown
            fallback_md = f"""## 1. Executive Summary
This research investigation examined **{question}** based on {len(sources)} collected web sources.

## 2. Key Findings
"""
            for s in sources[:5]:
                fallback_md += f"- **{s.get('title', 'Finding')}**: {s.get('why_relevant', '')} [{s.get('id', 1)}]\n"

            fallback_md += f"""
## 3. Detailed Analysis
The collected web sources provide empirical coverage for the investigated topic.

## 4. Multi-Source Comparison
Sources were retrieved across multiple independent domains including: {', '.join(set(s.get('domain', '') for s in sources))}.

## 5. Limitations
Report compiled under resilient fallback mode.
"""
            return GeneratedReport(
                markdown_content=fallback_md,
                citation_count=len(sources),
                sections=["Executive Summary", "Key Findings", "Detailed Analysis", "Limitations"],
            )
