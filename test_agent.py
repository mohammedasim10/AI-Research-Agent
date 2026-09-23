"""
test_agent.py - Comprehensive Unit and Component Tests for ResearchAI.
Tests configuration validation, domain-aware planning, web search retrieval,
source categorization, diversity metrics, content extraction, and multi-format exports.
"""

import os
import unittest
from config import AppConfig
from planner import ResearchPlanner
from search import SearchClient
from source_processor import SourceProcessor
from utils.helpers import (
    classify_source_type,
    calculate_source_diversity,
    clean_text,
    extract_domain,
    truncate_text,
    build_markdown_report_export,
    build_text_report_export,
    build_html_printable_export,
    build_json_export,
)


class TestConfig(unittest.TestCase):
    def test_missing_api_key_raises(self):
        cfg = AppConfig(gemini_api_key=None)
        with self.assertRaises(ValueError):
            cfg.validate_api_key(None)

    def test_valid_api_key_passes(self):
        cfg = AppConfig(gemini_api_key="valid_test_key_1234567890")
        self.assertEqual(cfg.validate_api_key(), "valid_test_key_1234567890")

    def test_too_short_key_raises(self):
        cfg = AppConfig(gemini_api_key="short")
        with self.assertRaises(ValueError):
            cfg.validate_api_key()


class TestHelpersAndClassification(unittest.TestCase):
    def test_extract_domain(self):
        self.assertEqual(extract_domain("https://www.nature.com/articles/s41586"), "nature.com")
        self.assertEqual(extract_domain("http://github.com/google/genai"), "github.com")
        self.assertEqual(extract_domain(""), "Unknown Source")

    def test_classify_source_type(self):
        self.assertEqual(classify_source_type("who.int"), "Government / Public Health Org")
        self.assertEqual(classify_source_type("cdc.gov"), "Government / Public Health Org")
        self.assertEqual(classify_source_type("nature.com"), "Scientific Journal / Peer-Reviewed")
        self.assertEqual(classify_source_type("stanford.edu"), "Academic / University")
        self.assertEqual(classify_source_type("docs.python.org"), "Official Tech Documentation")
        self.assertEqual(classify_source_type("reuters.com"), "News & Analysis")

    def test_calculate_source_diversity(self):
        sources = [
            {"domain": "who.int", "url": "https://who.int/news/1"},
            {"domain": "nature.com", "url": "https://nature.com/articles/2"},
            {"domain": "stanford.edu", "url": "https://stanford.edu/research/3"},
        ]
        div = calculate_source_diversity(sources)
        self.assertEqual(div["distinct_type_count"], 3)
        self.assertTrue(div["is_diverse"])

    def test_clean_text(self):
        raw = "Hello \x00 world \n\n\n\n test    spaces"
        cleaned = clean_text(raw)
        self.assertEqual(cleaned, "Hello world\n\ntest spaces")

    def test_truncate_text(self):
        text = "Autonomous AI agents perform multi-step planning and web retrieval."
        truncated = truncate_text(text, max_chars=25)
        self.assertTrue(truncated.endswith("..."))
        self.assertTrue(len(truncated) <= 28)

    def test_multi_format_exports(self):
        sources = [{"id": 1, "title": "RAG Paper", "url": "https://arxiv.org/abs/2005.11401", "domain": "arxiv.org"}]
        md = build_markdown_report_export(
            question="What is RAG?",
            report_content="## Summary\nRAG connects LLMs to external data [1].",
            sources=sources,
        )
        self.assertIn("# ResearchAI Intelligence Dossier: What is RAG?", md)
        self.assertIn("[1] [RAG Paper](https://arxiv.org/abs/2005.11401)", md)

        txt = build_text_report_export(
            question="What is RAG?",
            report_content="RAG Summary",
            sources=sources,
        )
        self.assertIn("RESEARCHAI DOSSIER: WHAT IS RAG?", txt)

        html = build_html_printable_export(
            question="What is RAG?",
            report_content_html="<p>RAG Summary</p>",
            sources=sources,
        )
        self.assertIn("ResearchAI Intelligence Dossier", html)
        self.assertIn("arxiv.org", html)

        js = build_json_export(
            question="What is RAG?",
            plan={"queries": ["RAG definition"]},
            report="RAG content",
            sources=sources,
            contradictions=[],
            metrics={"duration": 1.2},
        )
        self.assertIn('"application": "ResearchAI"', js)
        self.assertIn('"query": "What is RAG?"', js)


class TestSearchClient(unittest.TestCase):
    def test_search_client_live_query(self):
        client = SearchClient(timeout=8, max_results_per_query=2)
        results = client.search_single_query("Python programming language", max_results=2)
        self.assertIsInstance(results, list)
        if results:
            first = results[0]
            self.assertTrue(hasattr(first, "title"))
            self.assertTrue(hasattr(first, "url"))
            self.assertTrue(hasattr(first, "domain"))
            self.assertTrue(len(first.url) > 0)


class TestSourceProcessor(unittest.TestCase):
    def test_html_extraction(self):
        processor = SourceProcessor(timeout=5)
        html = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <header><nav>Navigation Link</nav></header>
                <h1>Deep Learning in Healthcare</h1>
                <p>Deep learning algorithms have demonstrated diagnostic accuracy comparable to human experts in medical imaging.</p>
                <footer>Copyright 2026</footer>
            </body>
        </html>
        """
        extracted = processor._extract_with_bs4(html)
        self.assertIn("Deep Learning in Healthcare", extracted)
        self.assertIn("diagnostic accuracy comparable to human experts", extracted)
        self.assertNotIn("Navigation Link", extracted)
        self.assertNotIn("Copyright 2026", extracted)


class TestDomainAwarePlanner(unittest.TestCase):
    def test_heuristic_domain_detection(self):
        planner = ResearchPlanner(api_key="mock_key_for_testing_heuristics")
        self.assertEqual(planner._detect_domain_heuristics("How is AI transforming modern healthcare?"), "Healthcare & Medicine")
        self.assertEqual(planner._detect_domain_heuristics("Explain climate change and global emissions"), "Climate & Environment")
        self.assertEqual(planner._detect_domain_heuristics("How does RAG work in machine learning?"), "Technology & Computer Science")
        self.assertEqual(planner._detect_domain_heuristics("What causes inflation in global markets?"), "Finance & Economics")


class TestVoiceHandler(unittest.TestCase):
    def test_voice_handler_empty_bytes_handling(self):
        from voice_handler import transcribe_voice_message
        text, lang = transcribe_voice_message(b"", mime_type="audio/ogg")
        self.assertIsNone(text)
        self.assertIsNone(lang)


class TestAgentFollowup(unittest.TestCase):
    def test_followup_empty_returns_original(self):
        from agent import ResearchAgent, ResearchSessionResult
        agent = ResearchAgent(api_key="mock_key_for_testing_heuristics_1234567")
        dummy_session = ResearchSessionResult(
            question="What is RAG?",
            success=True,
            plan=None,
            sources=[],
            analysis=None,
            report_markdown="RAG Report",
            teaching_markdown="RAG Guide",
            language="en",
        )
        res = agent.answer_followup(dummy_session, "")
        self.assertEqual(res.question, "What is RAG?")


if __name__ == "__main__":
    unittest.main()


