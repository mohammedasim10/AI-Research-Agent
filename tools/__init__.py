"""
tools package - Controlled agent tool subsystem.
"""

from tools.base import BaseTool, ToolParameter, ToolResult, ToolRegistry
from tools.web_search import WebSearchTool
from tools.scraper import ScraperTool
from tools.calculator import CalculatorTool, SafeMathEvaluator

__all__ = [
    "BaseTool",
    "ToolParameter",
    "ToolResult",
    "ToolRegistry",
    "WebSearchTool",
    "ScraperTool",
    "CalculatorTool",
    "SafeMathEvaluator",
    "get_default_registry",
]


def get_default_registry() -> ToolRegistry:
    """Instantiates and populates standard tool registry for ResearchAI."""
    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(ScraperTool())
    registry.register(CalculatorTool())
    return registry
