"""
agent.py - ResearchAI Autonomous Orchestrator Agent.
Coordinates the end-to-end research lifecycle:
Plan -> Search -> Collect -> Rank/RAG -> Analyze -> Cross-Check -> Synthesize -> Verify Citations -> Report
Provides real-time event streaming callbacks, multilingual adaptation, and pedagogical teaching.
"""

from dataclasses import dataclass, field, asdict
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from analyzer import ResearchAnalyzer, SourceAnalysisResult
from citation_verifier import CitationVerifier, CitationVerificationResult
from config import AppConfig, config as default_config
from observability import metrics_registry, trace_operation, create_request_context
from planner import ResearchPlan, ResearchPlanner
from rag_engine import RAGEngine, RAGContext
from report_generator import GeneratedReport, ResearchReportGenerator, SUPPORTED_LANGUAGES
from search import SearchClient, SearchResult
from source_processor import ProcessedSource, SourceProcessor
from tools import ToolRegistry, get_default_registry

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
    citation_verification: Optional[Dict[str, Any]] = None
    rag_metadata: Optional[Dict[str, Any]] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    language_cache: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ResearchAgent:
    """
    Autonomous multi-stage AI Research Agent powered by Google Gemini and live web retrieval.
    Includes pedagogical tutoring, RAG context ranking, deterministic citation verification,
    and multilingual adaptation across English, Hindi, Telugu, and Arabic.
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
        
        # New Engineering Subsystems
        self.rag_engine = RAGEngine(max_context_chars=24000)
        self.citation_verifier = CitationVerifier()
        self.tool_registry = get_default_registry()

    def run(
        self,
        question: str,
        language: str = "en",
        mode: str = "deep",
        on_progress: Optional[Callable[[str, str, str, Optional[Dict[str, Any]]], None]] = None,
        user_id: Any = None,
    ) -> ResearchSessionResult:
        """
        Executes the full autonomous research pipeline with real-time progress callbacks.
        """
        start_time = time.time()
        clean_question = question.strip()
        lang_code = language if language in SUPPORTED_LANGUAGES else "en"
        req_ctx = create_request_context(action="research_session", user_id=user_id, question=clean_question)

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
                metrics={"duration_seconds": 0, "request_id": req_ctx.request_id},
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
                dur = round(time.time() - start_time, 2)
                metrics_registry.record_request(
                    action="research_session",
                    success=False,
                    duration_seconds=dur,
                    model_name=self.model_name,
                )
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
                    metrics={"duration_seconds": dur, "request_id": req_ctx.request_id},
                    error_message="Web search returned 0 results. Please try rephrasing your research question.",
                )

            notify(
                "search",
                "completed",
                f"Retrieved {len(search_hits)} distinct web sources across {len(set(h.domain for h in search_hits))} domains.",
                {"results_count": len(search_hits)},
            )

            # -------------------------------------------------------------
            # STAGE 3: CONTENT EXTRACTION & NORMALIZATION (SSRF PROTECTED)
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
            # STAGE 4: RAG CONTEXT RANKING & DOMAIN SCORING
            # -------------------------------------------------------------
            notify("rag", "running", "Ranking sources by domain authority and building token-budgeted RAG context...")
            rag_context: RAGContext = self.rag_engine.construct_rag_context(
                question=clean_question,
                sources=[s.to_dict() for s in processed_sources],
                search_queries=plan.search_queries,
            )
            notify(
                "rag",
                "completed",
                f"Ranked {len(rag_context.ranked_sources)} sources. Covered {len(rag_context.domains_covered)} authoritative domains.",
                {"est_tokens": rag_context.total_tokens_estimated},
            )

            # -------------------------------------------------------------
            # STAGE 5: CROSS-SOURCE ANALYSIS & CONTRADICTION DETECTION
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
            # STAGE 6: REPORT SYNTHESIS WITH CITATION GROUNDING & TEACHING
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

            # -------------------------------------------------------------
            # STAGE 7: POST-GENERATION DETERMINISTIC CITATION VERIFICATION
            # -------------------------------------------------------------
            notify("verify", "running", "Executing deterministic citation verification and scrubbing hallucinated references...")
            verification: CitationVerificationResult = self.citation_verifier.verify_citations(
                markdown_text=report_data.markdown_content,
                sources=analysis_result.enriched_sources,
            )
            final_report_markdown = verification.verified_markdown or report_data.markdown_content
            notify(
                "verify",
                "completed",
                f"Citation verification passed. Grounding rate: {verification.grounding_rate*100:.1f}%, {verification.valid_citations_count} valid citations.",
                {"grounding_rate": verification.grounding_rate},
            )

            duration = round(time.time() - start_time, 2)
            total_words = sum(s.get("word_count", 0) for s in analysis_result.enriched_sources)

            metrics = {
                "duration_seconds": duration,
                "request_id": req_ctx.request_id,
                "queries_executed": len(plan.search_queries),
                "sources_retrieved": len(processed_sources),
                "full_text_extracts": successful_fetches,
                "total_words_analyzed": total_words,
                "citations_referenced": verification.valid_citations_count,
                "grounding_rate_percent": round(verification.grounding_rate * 100, 2),
                "domains_covered_count": len(rag_context.domains_covered),
                "model_used": self.model_name,
                "language": lang_code,
                "mode": mode,
            }

            # Record operational observability metrics
            metrics_registry.record_request(
                action="research_session",
                success=True,
                duration_seconds=duration,
                model_name=self.model_name,
                sources_count=len(processed_sources),
                citations_count=verification.total_citations_found,
                grounded_count=verification.valid_citations_count,
            )

            # Cache current language
            lang_cache = {
                lang_code: {
                    "report_markdown": final_report_markdown,
                    "teaching_markdown": report_data.teaching_content,
                }
            }

            rag_meta = {
                "domains_covered": rag_context.domains_covered,
                "source_types": rag_context.source_types_represented,
                "est_context_tokens": rag_context.total_tokens_estimated,
            }

            return ResearchSessionResult(
                question=clean_question,
                success=True,
                plan=plan.to_dict(),
                sources=analysis_result.enriched_sources,
                analysis=analysis_result.to_dict(),
                report_markdown=final_report_markdown,
                teaching_markdown=report_data.teaching_content,
                language=lang_code,
                mode=mode,
                citation_verification=verification.to_dict(),
                rag_metadata=rag_meta,
                metrics=metrics,
                language_cache=lang_cache,
            )

        except Exception as exc:
            logger.exception("Unexpected error during research execution:")
            duration = round(time.time() - start_time, 2)
            metrics_registry.record_request(
                action="research_session",
                success=False,
                duration_seconds=duration,
                model_name=self.model_name,
            )
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
                metrics={"duration_seconds": duration, "request_id": req_ctx.request_id},
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
        user_id: Any = None,
    ) -> ResearchSessionResult:
        """
        Processes a contextual follow-up question, preserving the original research foundation
        while addressing the specific follow-up topic directly.
        """
        clean_followup = followup_question.strip()
        if not clean_followup:
            return original_session

        contextual_target = f"{original_session.question} (Follow-up: {clean_followup})"
        return self.run(
            question=contextual_target,
            language=language,
            mode=mode,
            on_progress=on_progress,
            user_id=user_id,
        )
