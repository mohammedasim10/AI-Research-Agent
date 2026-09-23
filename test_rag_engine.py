"""
test_rag_engine.py - Unit tests for RAG Context Construction and Source Ranking Engine.
"""

import unittest
from rag_engine import RAGEngine, DOMAIN_AUTHORITY_WEIGHTS


class TestRAGEngine(unittest.TestCase):
    """Tests for source scoring, domain authority hierarchy, and context budgeting."""

    def setUp(self):
        self.rag = RAGEngine(max_context_chars=2000, max_passages_per_source=2)
        self.sample_sources = [
            {
                "id": 1,
                "title": "Random Blog Post on Tech",
                "url": "https://randomblog.com/post/123",
                "domain": "randomblog.com",
                "snippet": "Artificial intelligence is changing the future of computing.",
                "full_text": "Artificial intelligence is changing the future of computing with new deep learning models.",
            },
            {
                "id": 2,
                "title": "NIH Clinical Trial Guidelines for Gene Therapy",
                "url": "https://www.nih.gov/clinical-trials/gene-therapy",
                "domain": "nih.gov",
                "snippet": "National Institutes of Health protocols on CRISPR Cas9 gene therapy in clinical trials.",
                "full_text": "National Institutes of Health protocols on CRISPR Cas9 gene therapy in clinical trials for sickle cell disease.",
            },
            {
                "id": 3,
                "title": "Nature Medicine: CRISPR Base Editing in Hematology",
                "url": "https://www.nature.com/articles/nm-crispr-2024",
                "domain": "nature.com",
                "snippet": "Clinical outcomes of base editing in patient cohorts.",
                "full_text": "Clinical outcomes of base editing in patient cohorts demonstrate high efficacy without double-strand DNA breaks.",
            },
        ]

    def test_domain_authority_ranking(self):
        question = "What are the latest CRISPR gene therapy clinical protocols?"
        ranked = self.rag.rank_and_score_sources(question, self.sample_sources)

        # NIH (Gov) and Nature (Journal) should rank higher than random blog
        self.assertGreater(ranked[0].authority_score, 0.90)
        self.assertEqual(ranked[-1].domain, "randomblog.com")

    def test_rag_context_construction(self):
        question = "CRISPR gene therapy"
        rag_context = self.rag.construct_rag_context(question, self.sample_sources)

        self.assertIn("nih.gov", rag_context.domains_covered)
        self.assertIn("nature.com", rag_context.domains_covered)
        self.assertGreater(rag_context.total_tokens_estimated, 10)
        self.assertIn("### [SOURCE 1]", rag_context.formatted_context_str)

    def test_budget_truncation(self):
        # Create small budget RAG engine
        tiny_rag = RAGEngine(max_context_chars=300)
        rag_context = tiny_rag.construct_rag_context("CRISPR", self.sample_sources)
        self.assertLessEqual(len(rag_context.formatted_context_str), 600)


if __name__ == "__main__":
    unittest.main()
