"""
test_citation_verifier.py - Unit tests for Citation Verification Subsystem.
"""

import unittest
from citation_verifier import CitationVerifier, CitationVerificationResult


class TestCitationVerifier(unittest.TestCase):
    """Tests for deterministic citation verification, precision, and hallucination scrubbing."""

    def setUp(self):
        self.verifier = CitationVerifier(min_lexical_overlap_threshold=0.05)
        self.mock_sources = [
            {
                "id": 1,
                "title": "GLP-1 receptor agonists in diabetes and weight loss",
                "url": "https://www.nature.com/articles/glp1-review",
                "domain": "nature.com",
                "full_text": "GLP-1 receptor agonists enhance glucose-dependent insulin secretion and delay gastric emptying.",
                "snippet": "GLP-1 receptor agonists enhance insulin secretion.",
            },
            {
                "id": 2,
                "title": "Cardiovascular outcomes of Semaglutide",
                "url": "https://www.nejm.org/doi/full/semaglutide-cv",
                "domain": "nejm.org",
                "full_text": "Semaglutide significantly reduces major adverse cardiovascular events in high-risk patients.",
                "snippet": "Reduces major cardiovascular events.",
            },
        ]

    def test_valid_citations_all_pass(self):
        text = (
            "GLP-1 agonists stimulate insulin secretion [1]. "
            "Furthermore, semaglutide reduces major cardiovascular events in trials [2]."
        )
        res = self.verifier.verify_citations(text, self.mock_sources)
        self.assertTrue(res.is_grounded)
        self.assertEqual(res.total_citations_found, 2)
        self.assertEqual(res.valid_citations_count, 2)
        self.assertEqual(res.invalid_citations_count, 0)
        self.assertEqual(res.grounding_rate, 1.0)
        self.assertEqual(res.unique_sources_cited, [1, 2])
        self.assertEqual(res.unreferenced_sources, [])

    def test_hallucinated_citation_detected_and_scrubbed(self):
        text = (
            "GLP-1 stimulates insulin [1]. "
            "Another study showed 99% cure rate [99]. "
            "Semaglutide prevents heart attacks [2]."
        )
        res = self.verifier.verify_citations(text, self.mock_sources)
        self.assertFalse(res.is_grounded)
        self.assertEqual(res.total_citations_found, 3)
        self.assertEqual(res.valid_citations_count, 2)
        self.assertEqual(res.invalid_citations_count, 1)
        self.assertEqual(res.hallucinated_indices, [99])
        self.assertIn(99, res.hallucinated_indices)
        
        # Verify [99] was scrubbed from verified_markdown
        self.assertNotIn("[99]", res.verified_markdown)
        self.assertIn("[1]", res.verified_markdown)
        self.assertIn("[2]", res.verified_markdown)

    def test_unreferenced_sources_tracking(self):
        text = "GLP-1 receptor agonists stimulate insulin secretion [1]."
        res = self.verifier.verify_citations(text, self.mock_sources)
        self.assertTrue(res.is_grounded)
        self.assertEqual(res.unique_sources_cited, [1])
        self.assertEqual(res.unreferenced_sources, [2])

    def test_empty_text_handling(self):
        res = self.verifier.verify_citations("", self.mock_sources)
        self.assertTrue(res.is_grounded)
        self.assertEqual(res.total_citations_found, 0)


if __name__ == "__main__":
    unittest.main()
