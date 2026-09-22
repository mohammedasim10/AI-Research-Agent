"""
report_generator.py - Academic & Enterprise Research Report Synthesis with Multilingual Teaching.
Produces structured, citation-grounded research reports and pedagogical "Understand This Topic"
explanations across English, Hindi, Telugu, and Arabic.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional
from analyzer import SourceAnalysisResult
from planner import ResearchPlan

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native": "English", "dir": "ltr"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "dir": "ltr"},
    "te": {"name": "Telugu", "native": "తెలుగు", "dir": "ltr"},
    "ar": {"name": "Arabic", "native": "العربية", "dir": "rtl"},
}


@dataclass
class GeneratedReport:
    """The finalized research report containing structured markdown content."""
    markdown_content: str
    teaching_content: str
    citation_count: int
    language: str = "en"
    mode: str = "deep"  # "simple" or "deep"
    sections: List[str] = field(default_factory=list)


class ResearchReportGenerator:
    """
    Generates structured, highly readable research reports and pedagogical explanations
    using Gemini LLM. Supports English, Hindi, Telugu, and Arabic with strict citation grounding.
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

    def _build_language_instruction(self, lang_code: str) -> str:
        """Constructs target language prompt rules."""
        lang_info = SUPPORTED_LANGUAGES.get(lang_code, SUPPORTED_LANGUAGES["en"])
        native_name = lang_info["native"]
        english_name = lang_info["name"]

        if lang_code == "en":
            return "Generate all content in standard, clear English."
        elif lang_code == "hi":
            return (
                "TARGET LANGUAGE: Natural modern Hindi (हिन्दी) in proper Unicode script. "
                "Do NOT use awkward literal machine translations. "
                "Keep scientific, technical, company, and product terms with their English names in parentheses "
                "where appropriate, e.g. मशीन लर्निंग (Machine Learning), आर्टिफिशियल इंटेलिजेंस (Artificial Intelligence). "
                "Ensure smooth, conversational yet authoritative Hindi phrasing."
            )
        elif lang_code == "te":
            return (
                "TARGET LANGUAGE: Natural modern Telugu (తెలుగు) in proper Unicode script. "
                "Do NOT use awkward machine-like literal translations. "
                "Keep technical terms, company names, and scientific concepts with their English names in parentheses "
                "where appropriate, e.g. ఆర్టిఫిషియల్ ఇంటెలిజెన్స్ (Artificial Intelligence), మెషిన్ లెర్నింగ్ (Machine Learning). "
                "Ensure fluent, informative Telugu prose."
            )
        elif lang_code == "ar":
            return (
                "TARGET LANGUAGE: Modern Standard Arabic (العربية الفصحى) in proper Unicode script. "
                "Ensure grammatically correct, eloquent, and natural Arabic terminology. "
                "Keep company names, scientific acronyms, and product terms accompanied by their English equivalents "
                "where useful. Ensure text flow suits right-to-left layout."
            )
        return f"Generate all content in {english_name} ({native_name})."

    def generate_report(
        self,
        question: str,
        plan: ResearchPlan,
        analysis_result: SourceAnalysisResult,
        language: str = "en",
        mode: str = "deep",  # "simple" or "deep"
    ) -> GeneratedReport:
        """
        Compiles the analyzed evidence into a cohesive, publication-quality report
        and an intelligent "Understand This Topic" tutor module.
        """
        sources = analysis_result.enriched_sources
        lang_code = language if language in SUPPORTED_LANGUAGES else "en"
        lang_instruction = self._build_language_instruction(lang_code)

        # Format source context with clear IDs for strict citation mapping
        sources_context = []
        for src in sources:
            src_id = src.get("id", 1)
            title = src.get("title", "Untitled")
            domain = src.get("domain", "")
            url = src.get("url", "")
            
            raw_facts = src.get("extracted_facts") or src.get("claims_supported") or src.get("extracted_evidence") or src.get("snippet") or ""
            if isinstance(raw_facts, str):
                raw_facts = [raw_facts] if raw_facts else ["Context retrieved from source."]
            elif isinstance(raw_facts, list):
                raw_facts = [str(f) for f in raw_facts if f]
            else:
                raw_facts = ["Context retrieved from source."]
                
            facts_str = "\n  - ".join(raw_facts) if raw_facts else "Context retrieved."
            sources_context.append(
                f"[Source {src_id}]\n"
                f"Title: {title}\n"
                f"Domain: {domain}\n"
                f"URL: {url}\n"
                f"Extracted Evidence:\n  - {facts_str}\n"
            )
        formatted_sources_block = "\n".join(sources_context)

        raw_consensus = analysis_result.consensus_findings or []
        if isinstance(raw_consensus, str):
            raw_consensus = [raw_consensus]
        consensus_block = "\n- ".join([str(c) for c in raw_consensus if c]) if raw_consensus else "None identified."

        contradictions_block = ""
        if analysis_result.contradictions_and_divergences:
            for item in analysis_result.contradictions_and_divergences:
                contradictions_block += f"- **{item.get('topic', 'Discrepancy')}**: {item.get('discrepancy', '')} (Sources: {item.get('involved_sources', [])})\n"
        else:
            contradictions_block = "- No significant factual contradictions detected across the analyzed sources.\n"

        raw_gaps = analysis_result.evidence_gaps_and_limitations or []
        if isinstance(raw_gaps, str):
            raw_gaps = [raw_gaps]
        gaps_block = "\n- ".join([str(g) for g in raw_gaps if g]) if raw_gaps else "None specified."

        is_simple = mode == "simple"

        raw_dims = plan.research_dimensions or []
        if isinstance(raw_dims, str):
            raw_dims = [raw_dims]
        dims_str = ", ".join([str(d) for d in raw_dims if d]) if raw_dims else "Core Concepts"

        system_instruction = f"""You are ResearchAI, an elite research engine and intelligent academic tutor.
{lang_instruction}

STRICT CITATION RULES:
1. For empirical claims in the research report, cite sources using bracketed numbers [1], [2], [1, 3].
2. ONLY cite source IDs that actually exist in the provided sources list.
3. Never fabricate facts, benchmarks, or citations.
4. Clearly distinguish empirically sourced facts from analytical synthesis.
5. In the "Understand This Topic" tutor section, explain intuitively with everyday examples, breakdown of key terms, and step-by-step mechanics."""

        prompt = f"""Generate a two-part intelligence document for this investigation:
Part A: "UNDERSTAND THIS TOPIC" (Tutor & Learning Guide)
Part B: "RESEARCH INTELLIGENCE REPORT" (Deep Evidence-Backed Analysis)

RESEARCH QUESTION:
"{question}"

RESEARCH INTENT: {plan.intent_summary}
TARGET DIMENSIONS: {dims_str}
MODE: {'Explain Simply (Beginner-Friendly & Intuitive)' if is_simple else 'Deep Research (Comprehensive & Rigorous)'}

VERIFIED EVIDENCE & SOURCES:
{formatted_sources_block}

CROSS-SOURCE ANALYSIS SUMMARY:
Consensus Findings:
{consensus_block}

Contradictions & Discrepancies:
{contradictions_block}

Identified Evidence Limitations:
{gaps_block}

OUTPUT FORMAT REQUIREMENTS:
Write the complete output using Markdown headings (## and ###) in the target language:

=== PART A: UNDERSTAND THIS TOPIC ===
## 🎓 Understand This Topic: Simple Explanation & Guide

### 1. What is it? (Simple Explanation)
A clear, intuitive explanation answering the question in plain, accessible language.

### 2. Why Does It Matter?
Why this topic is important, its significance, and practical impact.

### 3. How Does It Work? (Step-by-Step)
Break down the underlying process into 3-4 simple, numbered steps.

### 4. Key Concepts & Important Terms
List 3-5 crucial terms. For each term, format as:
- **Term (English Term)**: Simple definition -> *Everyday Example*

### 5. Real-World Applications & Examples
Concrete practical examples of where and how this is used today.

### 6. Advantages & Key Limitations
- **Advantages**: 2-3 key benefits.
- **Limitations**: 2-3 constraints or challenges.

### 7. Key Takeaway
A short, memorable 1-2 sentence core message.

=== PART B: RESEARCH INTELLIGENCE REPORT ===
## 📊 Research Intelligence Report

## 1. Executive Summary
A concise synthesis answering the core research question directly. Cite primary evidence with [1], [2].

## 2. Key Findings
A clear list of 4-6 bulleted, high-impact takeaways with inline citations [1], [2] and bold lead-ins.

## 3. Detailed Analysis
Thorough multi-paragraph analytical breakdown covering the research dimensions. Organize with clear sub-headings (###). Every paragraph must integrate relevant citations.

## 4. Empirical Evidence & Supporting Data
A structured overview of specific metrics, case studies, benchmarks, and data points surfaced in the evidence.

## 5. Multi-Source Comparison & Discrepancies
An explicit comparison of perspectives across the collected sources. Highlight consensus and conflicting viewpoints.

## 6. Limitations & Evidence Gaps
Critical evaluation of the limitations of the current evidence base.

## 7. Strategic Outlook & Conclusion
A balanced, forward-looking summary.

(Do NOT generate the final Sources / References list in your response, as the application automatically attaches the interactive reference cards).
"""

        try:
            full_response = self._call_gemini_text(prompt, system_instruction)
            
            # Split Part A (Teaching) and Part B (Report) if separator or headings present
            teaching_part = ""
            report_part = ""

            if "=== PART B:" in full_response or "## 📊 Research Intelligence Report" in full_response:
                parts = re.split(r"(?:=== PART B:.*===|## 📊 Research Intelligence Report)", full_response, maxsplit=1)
                teaching_part = parts[0].replace("=== PART A: UNDERSTAND THIS TOPIC ===", "").strip()
                report_part = ("## 📊 Research Intelligence Report\n\n" + parts[1]).strip() if len(parts) > 1 else full_response
            else:
                teaching_part = full_response
                report_part = full_response

            citations = re.findall(r"\[\d+\]", full_response)
            
            return GeneratedReport(
                markdown_content=report_part,
                teaching_content=teaching_part,
                citation_count=len(citations),
                language=lang_code,
                mode=mode,
                sections=[
                    "Understand This Topic",
                    "Executive Summary",
                    "Key Findings",
                    "Detailed Analysis",
                    "Empirical Evidence",
                    "Multi-Source Comparison",
                    "Limitations",
                    "Conclusion",
                ],
            )

        except Exception as exc:
            logger.error(f"Error during report generation: {exc}")
            fallback_md = f"""## 📊 Research Report
### Research Question: {question}
Processed {len(sources)} sources for analysis.
"""
            for s in sources[:5]:
                fallback_md += f"- **{s.get('title', 'Finding')}**: {s.get('why_relevant', '')} [{s.get('id', 1)}]\n"

            return GeneratedReport(
                markdown_content=fallback_md,
                teaching_content=f"## 🎓 Understand This Topic\n\nInvestigation into **{question}** completed.",
                citation_count=len(sources),
                language=lang_code,
                mode=mode,
                sections=["Understand This Topic", "Executive Summary", "Key Findings"],
            )

    def translate_report(
        self,
        question: str,
        existing_report: GeneratedReport,
        target_language: str,
        sources: List[Dict[str, Any]],
    ) -> GeneratedReport:
        """
        Translates/adapts an existing report and teaching guide into the target language
        without executing a new web search, preserving all citations and factual evidence.
        """
        if target_language == existing_report.language:
            return existing_report

        lang_code = target_language if target_language in SUPPORTED_LANGUAGES else "en"
        lang_instruction = self._build_language_instruction(lang_code)

        system_instruction = f"""You are ResearchAI Multilingual Translation & Adaptation Engine.
{lang_instruction}

STRICT TRANSLATION RULES:
1. Preserve all citations EXACTLY as [1], [2], [3] in their original places.
2. Preserve all numbers, statistics, percentages, and metrics exactly.
3. Preserve all source URLs, domain names, and technical terms in English inside parentheses where helpful.
4. Translate both the "Understand This Topic" teaching section and the "Research Report" into high-quality, fluent {SUPPORTED_LANGUAGES[lang_code]['name']}.
5. Do NOT invent new facts or alter the research findings."""

        prompt = f"""Translate and adapt this complete research dossier into {SUPPORTED_LANGUAGES[lang_code]['name']} ({SUPPORTED_LANGUAGES[lang_code]['native']}):

ORIGINAL RESEARCH QUESTION: "{question}"

TEACHING CONTENT TO ADAPT:
{existing_report.teaching_content}

RESEARCH REPORT TO ADAPT:
{existing_report.markdown_content}

Output both sections clearly in {SUPPORTED_LANGUAGES[lang_code]['native']} using proper Markdown headings.
"""

        try:
            translated_text = self._call_gemini_text(prompt, system_instruction)
            
            teaching_part = ""
            report_part = ""

            if "## 📊" in translated_text or "Research Intelligence Report" in translated_text or "=== PART B" in translated_text:
                parts = re.split(r"(?:=== PART B:.*===|## 📊)", translated_text, maxsplit=1)
                teaching_part = parts[0].replace("=== PART A: UNDERSTAND THIS TOPIC ===", "").strip()
                report_part = ("## 📊 " + parts[1]).strip() if len(parts) > 1 else translated_text
            else:
                teaching_part = translated_text
                report_part = translated_text

            citations = re.findall(r"\[\d+\]", translated_text)

            return GeneratedReport(
                markdown_content=report_part,
                teaching_content=teaching_part,
                citation_count=len(citations) or existing_report.citation_count,
                language=lang_code,
                mode=existing_report.mode,
                sections=existing_report.sections,
            )
        except Exception as e:
            logger.error(f"Error during report translation: {e}")
            return existing_report
