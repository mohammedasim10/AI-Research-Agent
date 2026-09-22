"""
agent.py - ResearchAI Autonomous Orchestrator Agent.
Coordinates the end-to-end research lifecycle:
Plan -> Search -> Collect -> Analyze -> Cross-Check -> Synthesize -> Report
Provides real-time event streaming callbacks, multilingual adaptation, and pedagogical teaching.
"""

from dataclasses import dataclass, field, asdict
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from analyzer import ResearchAnalyzer, SourceAnalysisResult
from config import AppConfig, config as default_config
from planner import ResearchPlan, ResearchPlanner
from report_generator import GeneratedReport, ResearchReportGenerator, SUPPORTED_LANGUAGES
from search import SearchClient, SearchResult
from source_processor import ProcessedSource, SourceProcessor

logger = logging.getLogger(__name__)


@dataclass
class ResearchSessionResult:
    """Complete structured output of an autonomous research run."""
    question: str
    success: bool
    plan: Optional[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    analysis: Optional[Dict[str, Any]]
    report_markdown: str
    teaching_markdown: str = ""
    language: str = "en"
    mode: str = "deep"  # "simple" or "deep"
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    language_cache: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ResearchAgent:
    """
    Autonomous multi-stage AI Research Agent powered by Google Gemini and live web retrieval.
    Includes pedagogical tutoring and multilingual adaptation across English, Hindi, Telugu, and Arabic.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[AppConfig] = None,
    ):
        self.config = config or default_config
        self.api_key = self.config.validate_api_key(api_key)
        self.model_name = self.config.gemini_model

        # Initialize sub-modules
        self.planner = ResearchPlanner(api_key=self.api_key, model_name=self.model_name)
        self.search_client = SearchClient(
            timeout=self.config.search_timeout_seconds,
            max_results_per_query=self.config.max_results_per_query,
        )
        self.source_processor = SourceProcessor(
            timeout=self.config.fetch_timeout_seconds,
            max_chars=self.config.max_source_content_chars,
        )
        self.analyzer = ResearchAnalyzer(api_key=self.api_key, model_name=self.model_name)
        self.report_generator = ResearchReportGenerator(api_key=self.api_key, model_name=self.model_name)

    def run(
        self,
        question: str,
        language: str = "en",
        mode: str = "deep",
        on_progress: Optional[Callable[[str, str, str, Optional[Dict[str, Any]]], None]] = None,
    ) -> ResearchSessionResult:
        """
        Executes the full autonomous research pipeline with real-time progress callbacks.
        """
        start_time = time.time()
        clean_question = question.strip()
        lang_code = language if language in SUPPORTED_LANGUAGES else "en"

        def notify(stage: str, status: str, message: str, data: Optional[Dict[str, Any]] = None):
            if on_progress:
                try:
                    on_progress(stage, status, message, data)
                except Exception as cb_err:
                    logger.debug(f"Progress callback error: {cb_err}")

        if not clean_question:
            notify("validate", "failed", "Empty research question provided.")
            return ResearchSessionResult(
                question="",
                success=False,
                plan=None,
                sources=[],
                analysis=None,
                report_markdown="",
                teaching_markdown="",
                language=lang_code,
                mode=mode,
                metrics={"duration_seconds": 0},
                error_message="Please enter a non-empty research question.",
            )

        try:
            # -------------------------------------------------------------
            # STAGE 1: UNDERSTANDING & PLANNING
            # -------------------------------------------------------------
            notify("plan", "running", "Deconstructing research question and formulating search strategy...")
            plan = self.planner.plan_research(
                question=clean_question,
                max_queries=self.config.max_search_queries,
            )
            notify(
                "plan",
                "completed",
                f"Generated {len(plan.search_queries)} targeted search queries across {len(plan.research_dimensions)} dimensions.",
                {"plan": plan.to_dict()},
            )

            # -------------------------------------------------------------
            # STAGE 2: LIVE WEB SEARCH
            # -------------------------------------------------------------
            notify("search", "running", f"Executing web search across {len(plan.search_queries)} queries...")
            search_hits = self.search_client.search_multiple_queries(
                queries=plan.search_queries,
                max_total_results=self.config.max_total_sources,
            )

            if not search_hits:
                notify("search", "warning", "No live web results returned for these queries.")
                return ResearchSessionResult(
                    question=clean_question,
                    success=False,
                    plan=plan.to_dict(),
                    sources=[],
                    analysis=None,
                    report_markdown="",
                    teaching_markdown="",
                    language=lang_code,
                    mode=mode,
                    metrics={"duration_seconds": round(time.time() - start_time, 2)},
                    error_message="Web search returned 0 results. Please try rephrasing your research question.",
                )

            notify(
                "search",
                "completed",
                f"Retrieved {len(search_hits)} distinct web sources across {len(set(h.domain for h in search_hits))} domains.",
                {"results_count": len(search_hits)},
            )

            # -------------------------------------------------------------
            # STAGE 3: CONTENT EXTRACTION & NORMALIZATION
            # -------------------------------------------------------------
            notify("collect", "running", f"Extracting readable text & evidence from {len(search_hits)} sources...")
            processed_sources = self.source_processor.process_sources_concurrently(
                search_results=[h.to_dict() for h in search_hits],
                max_workers=5,
            )
            successful_fetches = sum(1 for s in processed_sources if s.status == "success")
            notify(
                "collect",
                "completed",
                f"Extracted content from {len(processed_sources)} sources ({successful_fetches} full-body extracts).",
                {"sources": [s.to_dict() for s in processed_sources]},
            )

            # -------------------------------------------------------------
            # STAGE 4: CROSS-SOURCE ANALYSIS & CONTRADICTION DETECTION
            # -------------------------------------------------------------
            notify("analyze", "running", "Cross-checking claims, detecting contradictions, and validating evidence...")
            analysis_result = self.analyzer.analyze_and_cross_check(
                question=clean_question,
                sources=processed_sources,
            )
            contradiction_count = len(analysis_result.contradictions_and_divergences)
            notify(
                "analyze",
                "completed",
                f"Cross-verification complete. Identified {len(analysis_result.consensus_findings)} consensus points and {contradiction_count} divergences.",
                {"analysis": analysis_result.to_dict()},
            )

            # -------------------------------------------------------------
            # STAGE 5: REPORT SYNTHESIS WITH CITATION GROUNDING & TEACHING
            # -------------------------------------------------------------
            lang_label = SUPPORTED_LANGUAGES[lang_code]["native"]
            notify("report", "running", f"Synthesizing research report & teaching guide in {lang_label}...")
            report_data = self.report_generator.generate_report(
                question=clean_question,
                plan=plan,
                analysis_result=analysis_result,
                language=lang_code,
                mode=mode,
            )
            notify(
                "report",
                "completed",
                f"Research report and tutor guide finalized with {report_data.citation_count} grounded citations.",
                {"citation_count": report_data.citation_count},
            )

            duration = round(time.time() - start_time, 2)
            total_words = sum(s["word_count"] for s in analysis_result.enriched_sources)

            metrics = {
                "duration_seconds": duration,
                "queries_executed": len(plan.search_queries),
                "sources_retrieved": len(processed_sources),
                "full_text_extracts": successful_fetches,
                "total_words_analyzed": total_words,
                "citations_referenced": report_data.citation_count,
                "model_used": self.model_name,
                "language": lang_code,
                "mode": mode,
            }

            # Cache current language
            lang_cache = {
                lang_code: {
                    "report_markdown": report_data.markdown_content,
                    "teaching_markdown": report_data.teaching_content,
                }
            }

            return ResearchSessionResult(
                question=clean_question,
                success=True,
                plan=plan.to_dict(),
                sources=analysis_result.enriched_sources,
                analysis=analysis_result.to_dict(),
                report_markdown=report_data.markdown_content,
                teaching_markdown=report_data.teaching_content,
                language=lang_code,
                mode=mode,
                metrics=metrics,
                language_cache=lang_cache,
            )

        except Exception as exc:
            logger.exception("Unexpected error during research execution:")
            duration = round(time.time() - start_time, 2)
            notify("error", "failed", f"Execution error: {str(exc)}")
            return ResearchSessionResult(
                question=clean_question,
                success=False,
                plan=None,
                sources=[],
                analysis=None,
                report_markdown="",
                teaching_markdown="",
                language=lang_code,
                mode=mode,
                metrics={"duration_seconds": duration},
                error_message=f"Research agent encountered an error: {str(exc)}",
            )

    def switch_language(
        self,
        session_result: ResearchSessionResult,
        target_language: str,
    ) -> ResearchSessionResult:
        """
        Switches/adapts the report and teaching guide into target language without re-searching.
        Uses cached translation if previously generated.
        """
        if not session_result.success or target_language == session_result.language:
            return session_result

        lang_code = target_language if target_language in SUPPORTED_LANGUAGES else "en"

        # Check cache
        if lang_code in session_result.language_cache:
            cached = session_result.language_cache[lang_code]
            session_result.report_markdown = cached["report_markdown"]
            session_result.teaching_markdown = cached["teaching_markdown"]
            session_result.language = lang_code
            session_result.metrics["language"] = lang_code
            return session_result

        # Reconstruct GeneratedReport for translation
        current_report = GeneratedReport(
            markdown_content=session_result.report_markdown,
            teaching_content=session_result.teaching_markdown,
            citation_count=session_result.metrics.get("citations_referenced", 0),
            language=session_result.language,
            mode=session_result.mode,
        )

        translated = self.report_generator.translate_report(
            question=session_result.question,
            existing_report=current_report,
            target_language=lang_code,
            sources=session_result.sources,
        )

        # Update cache and result
        session_result.language_cache[lang_code] = {
            "report_markdown": translated.markdown_content,
            "teaching_markdown": translated.teaching_content,
        }
        session_result.report_markdown = translated.markdown_content
        session_result.teaching_markdown = translated.teaching_content
        session_result.language = lang_code
        session_result.metrics["language"] = lang_code

        return session_result

    def answer_followup(
        self,
        original_session: ResearchSessionResult,
        followup_question: str,
        language: str = "en",
        mode: str = "deep",
        on_progress: Optional[Callable[[str, str, str, Optional[Dict[str, Any]]], None]] = None,
    ) -> ResearchSessionResult:
        """
        Processes a contextual follow-up question, preserving the original research foundation
        while addressing the specific follow-up topic directly.
        """
        clean_followup = followup_question.strip()
        if not clean_followup:
            return original_session

        # Formulate contextual investigation target
        contextual_target = f"{original_session.question} (Follow-up: {clean_followup})"
        return self.run(
            question=contextual_target,
            language=language,
            mode=mode,
            on_progress=on_progress,
        )

