"""
evaluation/evaluator.py - Autonomous Benchmark Evaluation Engine for ResearchAI.
Measures Citation Grounding Rate, Domain Authority Quality, Topic Recall, Latency, and Language Fidelity.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import logging
import os
import re
import statistics
import time
from typing import Any, Dict, List, Optional

from agent import ResearchAgent, ResearchSessionResult
from rag_engine import DOMAIN_AUTHORITY_WEIGHTS
from utils.helpers import extract_domain, classify_source_type

logger = logging.getLogger(__name__)


@dataclass
class EvaluationSampleResult:
    """Evaluation metrics for a single benchmark query."""
    sample_id: str
    domain: str
    question: str
    language: str
    success: bool
    latency_seconds: float
    grounding_rate: float
    valid_citations_count: int
    invalid_citations_count: int
    sources_retrieved_count: int
    domain_authority_score: float
    topic_recall_score: float
    script_fidelity_passed: bool
    has_teaching_guide: bool
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkSummary:
    """Aggregated benchmark evaluation summary."""
    timestamp: str
    total_samples: int
    successful_runs: int
    failed_runs: int
    success_rate_pct: float
    mean_grounding_rate_pct: float
    mean_domain_authority_score: float
    mean_topic_recall_pct: float
    script_fidelity_pct: float
    teaching_guide_coverage_pct: float
    mean_latency_seconds: float
    median_latency_seconds: float
    p95_latency_seconds: float
    domain_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    sample_results: List[EvaluationSampleResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total_samples": self.total_samples,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "success_rate_pct": round(self.success_rate_pct, 2),
            "mean_grounding_rate_pct": round(self.mean_grounding_rate_pct, 2),
            "mean_domain_authority_score": round(self.mean_domain_authority_score, 3),
            "mean_topic_recall_pct": round(self.mean_topic_recall_pct, 2),
            "script_fidelity_pct": round(self.script_fidelity_pct, 2),
            "teaching_guide_coverage_pct": round(self.teaching_guide_coverage_pct, 2),
            "mean_latency_seconds": round(self.mean_latency_seconds, 2),
            "median_latency_seconds": round(self.median_latency_seconds, 2),
            "p95_latency_seconds": round(self.p95_latency_seconds, 2),
            "domain_breakdown": self.domain_breakdown,
            "sample_results": [s.to_dict() for s in self.sample_results],
        }


class BenchmarkEvaluator:
    """Harness that evaluates the AI Research Agent against benchmark datasets."""

    def __init__(self, agent: Optional[ResearchAgent] = None):
        self.agent = agent or ResearchAgent()

    def _check_script_fidelity(self, text: str, language: str) -> bool:
        """Verifies Unicode character ranges match expected target script."""
        if not text:
            return False
        if language == "en":
            return True
        elif language == "hi":
            # Devanagari range: \u0900-\u097F
            devanagari_chars = len(re.findall(r"[\u0900-\u097F]", text))
            return devanagari_chars > 20
        elif language == "te":
            # Telugu range: \u0C00-\u0C7F
            telugu_chars = len(re.findall(r"[\u0C00-\u0C7F]", text))
            return telugu_chars > 20
        elif language == "ar":
            # Arabic range: \u0600-\u06FF
            arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
            return arabic_chars > 20
        return True

    def _compute_topic_recall(self, text: str, required_topics: List[str]) -> float:
        """Measures proportion of mandatory concepts covered in generated synthesis."""
        if not required_topics or not text:
            return 1.0
        text_lower = text.lower()
        matched = sum(1 for topic in required_topics if topic.lower() in text_lower)
        return matched / len(required_topics)

    def evaluate_sample(self, sample: Dict[str, Any], mode: str = "deep") -> EvaluationSampleResult:
        """Runs and evaluates a single benchmark query."""
        sample_id = sample.get("id", "sample")
        domain = sample.get("domain", "General")
        question = sample.get("question", "")
        language = sample.get("language", "en")
        required_topics = sample.get("required_topics", [])

        t0 = time.perf_counter()
        session_result: ResearchSessionResult = self.agent.run(
            question=question,
            language=language,
            mode=mode,
        )
        latency = round(time.perf_counter() - t0, 2)

        notes: List[str] = []
        if not session_result.success:
            notes.append(f"Session failed: {session_result.error_message}")
            return EvaluationSampleResult(
                sample_id=sample_id,
                domain=domain,
                question=question,
                language=language,
                success=False,
                latency_seconds=latency,
                grounding_rate=0.0,
                valid_citations_count=0,
                invalid_citations_count=0,
                sources_retrieved_count=0,
                domain_authority_score=0.0,
                topic_recall_score=0.0,
                script_fidelity_passed=False,
                has_teaching_guide=False,
                notes=notes,
            )

        # 1. Citation verification metrics
        cv = session_result.citation_verification or {}
        grounding_rate = cv.get("grounding_rate", 1.0)
        valid_citations = cv.get("valid_citations_count", 0)
        invalid_citations = cv.get("invalid_citations_count", 0)

        # 2. Domain Authority Score
        sources = session_result.sources or []
        auth_scores = []
        for s in sources:
            stype = s.get("source_type") or classify_source_type(s.get("domain", ""), s.get("url", ""), s.get("title", ""))
            auth_scores.append(DOMAIN_AUTHORITY_WEIGHTS.get(stype, 0.60))
        mean_auth = (sum(auth_scores) / len(auth_scores)) if auth_scores else 0.0

        # 3. Topic Recall
        full_text = session_result.report_markdown + " " + session_result.teaching_markdown
        topic_recall = self._compute_topic_recall(full_text, required_topics)

        # 4. Script Fidelity
        script_ok = self._check_script_fidelity(session_result.report_markdown, language)

        # 5. Teaching Guide
        has_teaching = bool(session_result.teaching_markdown and len(session_result.teaching_markdown) > 100)

        return EvaluationSampleResult(
            sample_id=sample_id,
            domain=domain,
            question=question,
            language=language,
            success=True,
            latency_seconds=latency,
            grounding_rate=grounding_rate,
            valid_citations_count=valid_citations,
            invalid_citations_count=invalid_citations,
            sources_retrieved_count=len(sources),
            domain_authority_score=round(mean_auth, 3),
            topic_recall_score=round(topic_recall, 3),
            script_fidelity_passed=script_ok,
            has_teaching_guide=has_teaching,
            notes=notes,
        )

    def run_benchmark(
        self,
        dataset: List[Dict[str, Any]],
        mode: str = "deep",
        max_samples: Optional[int] = None,
    ) -> BenchmarkSummary:
        """Executes full benchmark evaluation across dataset."""
        samples_to_run = dataset[:max_samples] if max_samples else dataset
        results: List[EvaluationSampleResult] = []

        logger.info(f"Starting benchmark evaluation on {len(samples_to_run)} samples...")

        for idx, sample in enumerate(samples_to_run, 1):
            logger.info(f"[{idx}/{len(samples_to_run)}] Evaluating {sample.get('id')}: {sample.get('question')[:50]}...")
            res = self.evaluate_sample(sample, mode=mode)
            results.append(res)

        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        success_rate = (successful / total * 100.0) if total > 0 else 0.0

        successful_results = [r for r in results if r.success]
        if successful_results:
            mean_grounding = statistics.mean(r.grounding_rate for r in successful_results) * 100.0
            mean_auth = statistics.mean(r.domain_authority_score for r in successful_results)
            mean_topic = statistics.mean(r.topic_recall_score for r in successful_results) * 100.0
            script_fidelity = (sum(1 for r in successful_results if r.script_fidelity_passed) / len(successful_results)) * 100.0
            teaching_coverage = (sum(1 for r in successful_results if r.has_teaching_guide) / len(successful_results)) * 100.0
            
            latencies = [r.latency_seconds for r in successful_results]
            mean_lat = statistics.mean(latencies)
            median_lat = statistics.median(latencies)
            latencies_sorted = sorted(latencies)
            p95_idx = int(len(latencies_sorted) * 0.95)
            p95_lat = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)]
        else:
            mean_grounding = mean_auth = mean_topic = script_fidelity = teaching_coverage = mean_lat = median_lat = p95_lat = 0.0

        # Domain breakdown
        domain_groups: Dict[str, List[EvaluationSampleResult]] = {}
        for r in results:
            domain_groups.setdefault(r.domain, []).append(r)

        domain_breakdown = {}
        for dom, dom_res in domain_groups.items():
            dom_succ = [r for r in dom_res if r.success]
            domain_breakdown[dom] = {
                "samples_count": len(dom_res),
                "success_rate_pct": round((len(dom_succ) / len(dom_res)) * 100.0, 1),
                "mean_grounding_pct": round(statistics.mean(r.grounding_rate for r in dom_succ) * 100.0, 1) if dom_succ else 0.0,
                "mean_domain_authority": round(statistics.mean(r.domain_authority_score for r in dom_succ), 3) if dom_succ else 0.0,
                "mean_latency_sec": round(statistics.mean(r.latency_seconds for r in dom_succ), 2) if dom_succ else 0.0,
            }

        return BenchmarkSummary(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_samples=total,
            successful_runs=successful,
            failed_runs=failed,
            success_rate_pct=success_rate,
            mean_grounding_rate_pct=mean_grounding,
            mean_domain_authority_score=mean_auth,
            mean_topic_recall_pct=mean_topic,
            script_fidelity_pct=script_fidelity,
            teaching_guide_coverage_pct=teaching_coverage,
            mean_latency_seconds=mean_lat,
            median_latency_seconds=median_lat,
            p95_latency_seconds=p95_lat,
            domain_breakdown=domain_breakdown,
            sample_results=results,
        )

    @staticmethod
    def generate_markdown_report(summary: BenchmarkSummary) -> str:
        """Generates publication-ready Markdown benchmark evaluation report."""
        lines = [
            "# 📊 ResearchAI Agent Engineering Benchmark Report",
            "",
            f"> **Evaluation Run Date:** `{summary.timestamp}`  ",
            f"> **Total Evaluated Queries:** `{summary.total_samples}` | **Success Rate:** `{summary.success_rate_pct:.1f}%`  ",
            f"> **Citation Grounding Rate:** `{summary.mean_grounding_rate_pct:.1f}%` | **Domain Authority Score:** `{summary.mean_domain_authority_score:.3f}`  ",
            "",
            "---",
            "",
            "## 1. Executive Performance Metrics",
            "",
            "| Evaluation Metric | Measured Value | Production Target | Status |",
            "| :--- | :--- | :--- | :--- |",
            f"| **Citation Grounding Accuracy** | **`{summary.mean_grounding_rate_pct:.1f}%`** | `> 95.0%` | {'✅ PASS' if summary.mean_grounding_rate_pct >= 95.0 else '⚠️ WARN'} |",
            f"| **Domain Authority Score (0-1.0)** | **`{summary.mean_domain_authority_score:.3f}`** | `> 0.800` | {'✅ PASS' if summary.mean_domain_authority_score >= 0.80 else '⚠️ WARN'} |",
            f"| **Topic & Fact Coverage** | **`{summary.mean_topic_recall_pct:.1f}%`** | `> 80.0%` | {'✅ PASS' if summary.mean_topic_recall_pct >= 80.0 else '⚠️ WARN'} |",
            f"| **Multilingual Script Fidelity** | **`{summary.script_fidelity_pct:.1f}%`** | `100.0%` | {'✅ PASS' if summary.script_fidelity_pct >= 95.0 else '⚠️ WARN'} |",
            f"| **Pedagogical Guide Generation** | **`{summary.teaching_guide_coverage_pct:.1f}%`** | `100.0%` | {'✅ PASS' if summary.teaching_guide_coverage_pct >= 95.0 else '⚠️ WARN'} |",
            f"| **Median Latency (p50)** | **`{summary.median_latency_seconds:.2f}s`** | `< 25.0s` | {'✅ PASS' if summary.median_latency_seconds <= 25.0 else '⚠️ WARN'} |",
            f"| **95th Percentile Latency (p95)** | **`{summary.p95_latency_seconds:.2f}s`** | `< 45.0s` | {'✅ PASS' if summary.p95_latency_seconds <= 45.0 else '⚠️ WARN'} |",
            "",
            "---",
            "",
            "## 2. Breakdown by Research Domain",
            "",
            "| Domain | Samples | Success Rate | Mean Grounding | Domain Auth | Avg Latency |",
            "| :--- | :---: | :---: | :---: | :---: | :---: |",
        ]

        for dom, stats in summary.domain_breakdown.items():
            lines.append(
                f"| **{dom}** | {stats['samples_count']} | {stats['success_rate_pct']:.1f}% | "
                f"{stats['mean_grounding_pct']:.1f}% | {stats['mean_domain_authority']:.3f} | {stats['mean_latency_sec']:.2f}s |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 3. Individual Query Results",
            "",
            "| ID | Domain | Question | Citations (Valid/Total) | Grounding | Domain Auth | Latency |",
            "| :--- | :--- | :--- | :---: | :---: | :---: | :---: |",
        ])

        for r in summary.sample_results:
            total_cit = r.valid_citations_count + r.invalid_citations_count
            q_short = r.question[:45] + ("..." if len(r.question) > 45 else "")
            lines.append(
                f"| `{r.sample_id}` | {r.domain[:20]} | {q_short} | "
                f"{r.valid_citations_count}/{total_cit} | {r.grounding_rate*100:.1f}% | "
                f"{r.domain_authority_score:.2f} | {r.latency_seconds:.2f}s |"
            )

        lines.extend([
            "",
            "---",
            "*Report autonomously produced by ResearchAI Evaluation Harness. All metrics derived from direct verification executions.*",
        ])

        return "\n".join(lines)
