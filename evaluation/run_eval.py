"""
evaluation/run_eval.py - CLI executable for running the benchmark evaluation suite.
"""

import argparse
import json
import logging
import os
import sys

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import ResearchAgent
from evaluation.evaluator import BenchmarkEvaluator, BenchmarkSummary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eval_runner")


def main():
    parser = argparse.ArgumentParser(description="Run ResearchAI Benchmark Evaluation Suite")
    parser.add_argument(
        "--dataset",
        default=os.path.join(os.path.dirname(__file__), "benchmark_dataset.json"),
        help="Path to benchmark JSON dataset",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Limit number of evaluation samples to execute",
    )
    parser.add_argument(
        "--mode",
        choices=["simple", "deep"],
        default="deep",
        help="Research mode to evaluate",
    )
    parser.add_argument(
        "--output-json",
        default=os.path.join(os.path.dirname(__file__), "evaluation_report.json"),
        help="Output path for JSON report",
    )
    parser.add_argument(
        "--output-md",
        default=os.path.join(os.path.dirname(__file__), "evaluation_report.md"),
        help="Output path for Markdown report",
    )

    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        logger.error(f"Dataset file not found: {args.dataset}")
        sys.exit(1)

    with open(args.dataset, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    logger.info(f"Loaded {len(dataset)} benchmark queries from {args.dataset}")

    agent = ResearchAgent()
    evaluator = BenchmarkEvaluator(agent=agent)
    summary: BenchmarkSummary = evaluator.run_benchmark(
        dataset=dataset,
        mode=args.mode,
        max_samples=args.max_samples,
    )

    # Save JSON report
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)
    logger.info(f"Saved evaluation JSON to {args.output_json}")

    # Save Markdown report
    md_content = BenchmarkEvaluator.generate_markdown_report(summary)
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info(f"Saved evaluation Markdown report to {args.output_md}")

    # Print summary table to stdout
    print("\n" + "=" * 80)
    print("RESEARCHAI BENCHMARK RESULTS SUMMARY")
    print("=" * 80)
    print(f"Total Evaluated:              {summary.total_samples}")
    print(f"Success Rate:                 {summary.success_rate_pct:.1f}%")
    print(f"Citation Grounding Accuracy:  {summary.mean_grounding_rate_pct:.1f}%")
    print(f"Domain Authority Score:       {summary.mean_domain_authority_score:.3f} / 1.000")
    print(f"Topic Recall / Fact Coverage: {summary.mean_topic_recall_pct:.1f}%")
    print(f"Multilingual Script Fidelity: {summary.script_fidelity_pct:.1f}%")
    print(f"Median Latency (p50):         {summary.median_latency_seconds:.2f}s")
    print(f"95th Percentile Latency(p95): {summary.p95_latency_seconds:.2f}s")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
