"""
test_evaluation.py - Unit tests for Benchmark Dataset and Evaluation Engine.
"""

import json
import os
import unittest
from evaluation.evaluator import BenchmarkEvaluator, BenchmarkSummary, EvaluationSampleResult


class TestEvaluationFramework(unittest.TestCase):
    """Tests for benchmark dataset integrity and evaluation metrics calculations."""

    def test_benchmark_dataset_integrity(self):
        dataset_path = os.path.join(os.path.dirname(__file__), "evaluation", "benchmark_dataset.json")
        self.assertTrue(os.path.exists(dataset_path), "Benchmark dataset JSON file must exist")

        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        self.assertGreaterEqual(len(dataset), 30, "Benchmark dataset must contain at least 30 questions")

        seen_ids = set()
        domains = set()
        languages = set()

        for idx, item in enumerate(dataset):
            self.assertIn("id", item)
            self.assertIn("domain", item)
            self.assertIn("question", item)
            self.assertIn("language", item)
            self.assertIn("required_topics", item)

            self.assertNotIn(item["id"], seen_ids, f"Duplicate ID: {item['id']}")
            seen_ids.add(item["id"])
            domains.add(item["domain"])
            languages.add(item["language"])

            self.assertTrue(len(item["question"].strip()) > 10, f"Question too short at index {idx}")
            self.assertTrue(len(item["required_topics"]) >= 2, f"Expected required topics at index {idx}")

        self.assertGreaterEqual(len(domains), 5, "Dataset must span at least 5 distinct domains")
        self.assertIn("hi", languages)
        self.assertIn("te", languages)
        self.assertIn("ar", languages)
        self.assertIn("en", languages)

    def test_evaluator_script_fidelity(self):
        evaluator = BenchmarkEvaluator()
        
        # Test Hindi Devanagari detection
        self.assertTrue(evaluator._check_script_fidelity("यह एक मशीन लर्निंग का विस्तृत शोध पत्र है। इसमें न्यूरल नेटवर्क के बारे में बताया गया है।", "hi"))
        self.assertFalse(evaluator._check_script_fidelity("This is purely english text without devanagari.", "hi"))

        # Test Telugu detection
        self.assertTrue(evaluator._check_script_fidelity("ఇది ఆర్టిఫిషియల్ ఇంటెలిజెన్స్ మరియు మెషిన్ లెర్నింగ్ పరిశోధనా నివేదిక.", "te"))
        self.assertFalse(evaluator._check_script_fidelity("This is plain english.", "te"))

        # Test Arabic detection
        self.assertTrue(evaluator._check_script_fidelity("هذا تقرير بحثي علمي شامل حول الذكاء الاصطناعي ومعالجة اللغات الطبيعية.", "ar"))
        self.assertFalse(evaluator._check_script_fidelity("English text here.", "ar"))

    def test_topic_recall_calculation(self):
        evaluator = BenchmarkEvaluator()
        text = "This report discusses mRNA vaccine durability, memory B cells, and neutralizing antibodies in clinical trials."
        topics = ["mRNA", "memory B cells", "neutralizing antibodies", "nonexistent topic"]

        recall = evaluator._compute_topic_recall(text, topics)
        self.assertEqual(recall, 0.75)

    def test_markdown_report_formatting(self):
        summary = BenchmarkSummary(
            timestamp="2026-09-23T12:00:00Z",
            total_samples=2,
            successful_runs=2,
            failed_runs=0,
            success_rate_pct=100.0,
            mean_grounding_rate_pct=98.5,
            mean_domain_authority_score=0.925,
            mean_topic_recall_pct=88.0,
            script_fidelity_pct=100.0,
            teaching_guide_coverage_pct=100.0,
            mean_latency_seconds=12.4,
            median_latency_seconds=12.0,
            p95_latency_seconds=14.0,
            domain_breakdown={
                "Healthcare & Medicine": {
                    "samples_count": 2,
                    "success_rate_pct": 100.0,
                    "mean_grounding_pct": 98.5,
                    "mean_domain_authority": 0.925,
                    "mean_latency_sec": 12.4,
                }
            },
            sample_results=[
                EvaluationSampleResult(
                    sample_id="eval-001",
                    domain="Healthcare & Medicine",
                    question="What is GLP-1 mechanism?",
                    language="en",
                    success=True,
                    latency_seconds=12.4,
                    grounding_rate=1.0,
                    valid_citations_count=3,
                    invalid_citations_count=0,
                    sources_retrieved_count=4,
                    domain_authority_score=0.95,
                    topic_recall_score=1.0,
                    script_fidelity_passed=True,
                    has_teaching_guide=True,
                )
            ],
        )

        md = BenchmarkEvaluator.generate_markdown_report(summary)
        self.assertIn("ResearchAI Agent Engineering Benchmark Report", md)
        self.assertIn("Healthcare & Medicine", md)
        self.assertIn("eval-001", md)


if __name__ == "__main__":
    unittest.main()
