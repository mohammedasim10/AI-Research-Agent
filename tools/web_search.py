"""
tools/web_search.py - Controlled Web Search Tool for Research Agent.
"""

from typing import Any, Dict, List, Optional
from search import SearchClient, SearchResult
from tools.base import BaseTool, ToolParameter


class WebSearchTool(BaseTool):
    """Executes targeted web search queries across authoritative sources."""

    def __init__(self, search_client: Optional[SearchClient] = None, timeout: int = 10):
        super().__init__(
            name="web_search",
            description="Searches the live web for verified facts, documents, statistics, and domain literature.",
            parameters=[
                ToolParameter(
                    name="query",
                    type_name="string",
                    description="The search query string to execute.",
                    required=True,
                ),
                ToolParameter(
                    name="max_results",
                    type_name="integer",
                    description="Maximum number of search results to retrieve (1-10).",
                    required=False,
                    default=5,
                ),
            ],
        )
        self.search_client = search_client or SearchClient(timeout=timeout)

    def _run(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Query cannot be empty")
        
        limit = min(max(1, int(max_results)), 10)
        results = self.search_client.search_single_query(clean_query, max_results=limit)
        return [r.to_dict() for r in results]
