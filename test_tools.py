"""
test_tools.py - Unit tests for the Controlled Tool Execution Subsystem.
"""

import unittest
from tools.base import BaseTool, ToolParameter, ToolResult, ToolRegistry
from tools.calculator import CalculatorTool, SafeMathEvaluator
from tools.scraper import ScraperTool
from tools.web_search import WebSearchTool
from utils.security import validate_url_for_ssrf, is_ip_blocked, mask_user_id


class TestSecurityUtilities(unittest.TestCase):
    """Tests for SSRF prevention and security functions."""

    def test_private_ip_blocking(self):
        self.assertTrue(is_ip_blocked("127.0.0.1"))
        self.assertTrue(is_ip_blocked("10.0.0.1"))
        self.assertTrue(is_ip_blocked("192.168.1.1"))
        self.assertTrue(is_ip_blocked("172.16.0.5"))
        self.assertTrue(is_ip_blocked("169.254.169.254"))  # Cloud metadata
        self.assertTrue(is_ip_blocked("::1"))

        # Public IP should not be blocked
        self.assertFalse(is_ip_blocked("8.8.8.8"))
        self.assertFalse(is_ip_blocked("1.1.1.1"))

    def test_ssrf_url_validation(self):
        # Malicious / internal URLs
        bad_urls = [
            "http://localhost/admin",
            "http://127.0.0.1:8000/keys",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.1.5/internal",
            "ftp://example.com/file",
            "file:///etc/passwd",
            "",
            None,
        ]
        for url in bad_urls:
            is_safe, reason = validate_url_for_ssrf(url, resolve_dns=False)
            self.assertFalse(is_safe, f"Expected {url} to be blocked, but passed: {reason}")

        # Safe public URL
        is_safe, reason = validate_url_for_ssrf("https://www.nature.com/articles/s41586-024", resolve_dns=False)
        self.assertTrue(is_safe)

    def test_user_id_masking(self):
        self.assertEqual(mask_user_id(123456789), "12***89")
        self.assertEqual(mask_user_id("987654321"), "98***21")
        self.assertEqual(mask_user_id(None), "anon")


class TestCalculatorTool(unittest.TestCase):
    """Tests for the Safe AST Calculator Tool."""

    def setUp(self):
        self.calc = CalculatorTool()
        self.evaluator = SafeMathEvaluator()

    def test_basic_arithmetic(self):
        self.assertEqual(self.evaluator.evaluate("2 + 2 * 3"), 8)
        self.assertEqual(self.evaluator.evaluate("(100 - 25) / 5"), 15.0)
        self.assertEqual(self.evaluator.evaluate("2 ** 8"), 256)

    def test_math_functions(self):
        self.assertEqual(self.evaluator.evaluate("sqrt(144)"), 12.0)
        self.assertEqual(self.evaluator.evaluate("abs(-42)"), 42)
        self.assertEqual(self.evaluator.evaluate("pct_change(100, 125)"), 25.0)
        self.assertEqual(self.evaluator.evaluate("mean([10, 20, 30, 40])"), 25.0)

    def test_dos_prevention(self):
        # Exponent too high should be rejected
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("2 ** 999999999")

    def test_eval_injection_rejection(self):
        # Arbitrary code execution attempts must fail
        malicious_inputs = [
            "__import__('os').system('ls')",
            "open('/etc/passwd').read()",
            "exec('x = 1')",
            "import os",
        ]
        for bad in malicious_inputs:
            with self.assertRaises(ValueError):
                self.evaluator.evaluate(bad)

    def test_tool_execute_interface(self):
        result = self.calc.execute(expression="(500 - 400) / 400 * 100")
        self.assertTrue(result.success)
        self.assertEqual(result.data["result"], 25.0)


class TestToolRegistry(unittest.TestCase):
    """Tests for ToolRegistry and schema generation."""

    def test_registry_lifecycle(self):
        reg = ToolRegistry()
        calc = CalculatorTool()
        reg.register(calc)

        self.assertIn("calculator", reg.list_tools())
        self.assertEqual(reg.get("calculator"), calc)

        # Test execute via registry
        res = reg.execute("calculator", expression="10 + 20")
        self.assertTrue(res.success)
        self.assertEqual(res.data["result"], 30)

        # Test non-existent tool
        res_bad = reg.execute("non_existent_tool")
        self.assertFalse(res_bad.success)
        self.assertIn("not found", res_bad.error)

    def test_scraper_ssrf_integration(self):
        scraper = ScraperTool()
        res = scraper.execute(url="http://127.0.0.1:5000/secret")
        self.assertFalse(res.success)
        self.assertIn("SSRF", res.error)


if __name__ == "__main__":
    unittest.main()
