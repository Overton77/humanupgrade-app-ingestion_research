"""
Tool Test Suite for Research Agent Search Integrations

This module provides a comprehensive test suite for various search and research tools
used in the biotech research agent. Run individual tests or all tests with custom queries.

Usage:
    # Run all tests with default biotech queries
    uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --all

    # Run a specific tool test
    uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --tool exa --query "CRISPR gene editing"

    # Run with custom query
    uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --tool serper --query "mRNA vaccine technology"

    # Run all tests with specific query type
    uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --all --query-type people

    # List available tools
    uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --list
"""

import os
import sys
import argparse
import pprint
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Search tools
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_community.tools import DuckDuckGoSearchResults, DuckDuckGoSearchRun
from langchain_exa import ExaSearchResults, ExaFindSimilarResults

# Academic/Scholarly tools
from langchain_community.tools.pubmed.tool import PubmedQueryRun
from langchain_community.tools.semanticscholar.tool import SemanticScholarQueryRun

# Finance tools
from langchain_community.tools.yahoo_finance_news import YahooFinanceNewsTool
from langchain_community.tools.google_finance import GoogleFinanceQueryRun
from langchain_community.utilities.google_finance import GoogleFinanceAPIWrapper
from langchain_community.tools.google_trends import GoogleTrendsQueryRun
from langchain_community.utilities.google_trends import GoogleTrendsAPIWrapper

from requests.exceptions import HTTPError

# Load environment variables
load_dotenv() 

os.environ["SERPAPI_API_KEY"] = os.getenv("SERP_API_KEY")

# Default biotech-related test queries
DEFAULT_BIOTECH_QUERIES = {
    "people": "Dr. Jennifer Doudna CRISPR research",
    "products": "mRNA vaccine technology Moderna",
    "topics": "gene therapy clinical trials 2024",
    "companies": "BioNTech biotech company",
    "research": "CAR-T cell therapy cancer treatment",
}


class ToolTestSuite:
    """Test suite for research agent search tools."""

    def __init__(self):
        """Initialize all tools with API keys from environment."""
        self.exa_api_key = os.getenv("EXA_API_KEY")
        self.serper_api_key = os.getenv("SERPER_API_KEY") 
        self.serp_api_key = os.getenv("SERP_API_KEY")
        
        # Initialize tools (will fail gracefully if API keys missing)
        self._init_tools()

    def _init_tools(self):
        """Initialize all search tools."""
        # Exa tools
        if self.exa_api_key:
            self.exa_search = ExaSearchResults(exa_api_key=self.exa_api_key)
            self.exa_find_similar = ExaFindSimilarResults(exa_api_key=self.exa_api_key)
        else:
            self.exa_search = None
            self.exa_find_similar = None

        # Google Serper
        if self.serper_api_key:
            self.serper_search = GoogleSerperAPIWrapper(serper_api_key=self.serper_api_key)
        else:
            self.serper_search = None

        # DuckDuckGo (no API key needed)
        self.ddg_search = DuckDuckGoSearchRun()
        self.ddg_search_results = DuckDuckGoSearchResults()

        # Academic tools (no API key needed)
        self.pubmed = PubmedQueryRun()
        self.semantic_scholar = SemanticScholarQueryRun()

        # Finance tools (no API key needed)
        self.yahoo_finance = YahooFinanceNewsTool()
        self.google_finance = GoogleFinanceQueryRun(api_wrapper=GoogleFinanceAPIWrapper())
        self.google_trends = GoogleTrendsQueryRun(api_wrapper=GoogleTrendsAPIWrapper())

    def test_exa_search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """Test Exa Search tool."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing Exa Search")
        print(f"{'='*80}")
        print(f"Query: {query}")
        print(f"Results requested: {num_results}\n")

        if not self.exa_search:
            return {"error": "EXA_API_KEY not set"}

        try:
            result = self.exa_search._run(
                query=query,
                num_results=num_results,
                text_contents_options=True,
                highlights=True,
            )
            print("✅ Exa Search succeeded!")
            print("\nResults:")
            pprint.pp(result, width=120)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ Exa Search failed: {e}")
            return {"success": False, "error": str(e)}

    def test_exa_find_similar(self, url: str, num_results: int = 5) -> Dict[str, Any]:
        """Test Exa Find Similar tool."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing Exa Find Similar")
        print(f"{'='*80}")
        print(f"URL: {url}")
        print(f"Results requested: {num_results}\n")

        if not self.exa_find_similar:
            return {"error": "EXA_API_KEY not set"}

        try:
            result = self.exa_find_similar._run(
                url=url,
                num_results=num_results,
                text_contents_options=True,
                highlights=True,
            )
            print("✅ Exa Find Similar succeeded!")
            print("\nResults:")
            pprint.pp(result, width=120)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ Exa Find Similar failed: {e}")
            return {"success": False, "error": str(e)}

    def test_serper(self, query: str) -> Dict[str, Any]:
        """Test Google Serper search."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing Google Serper")
        print(f"{'='*80}")
        print(f"Query: {query}\n")

        if not self.serper_search:
            return {"error": "SERPER_API_KEY not set"}

        try:
            result = self.serper_search.run(query)
            print("✅ Google Serper succeeded!")
            print("\nResult:")
            print(result)
            return {"success": True, "result": result}
        except HTTPError as e:
            print(f"❌ Google Serper HTTPError:")
            print(f"Status code: {e.response.status_code if e.response else 'unknown'}")
            try:
                body = e.response.text if e.response is not None else ""
            except Exception:
                body = "<unable to read response body>"
            print(f"Response body: {body}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"❌ Google Serper failed: {e}")
            return {"success": False, "error": str(e)}

    def test_duckduckgo(self, query: str) -> Dict[str, Any]:
        """Test DuckDuckGo search."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing DuckDuckGo Search")
        print(f"{'='*80}")
        print(f"Query: {query}\n")

        try:
            result = self.ddg_search.run(query)
            print("✅ DuckDuckGo Search succeeded!")
            print("\nResult:")
            print(result)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ DuckDuckGo Search failed: {e}")
            return {"success": False, "error": str(e)}

    def test_duckduckgo_results(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Test DuckDuckGo search results (structured)."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing DuckDuckGo Search Results")
        print(f"{'='*80}")
        print(f"Query: {query}")
        print(f"Max results: {max_results}\n")

        try:
            result = self.ddg_search_results.run(query)
            print("✅ DuckDuckGo Search Results succeeded!")
            print("\nResults:")
            pprint.pp(result, width=120)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ DuckDuckGo Search Results failed: {e}")
            return {"success": False, "error": str(e)}

    def test_pubmed(self, query: str) -> Dict[str, Any]:
        """Test PubMed search."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing PubMed")
        print(f"{'='*80}")
        print(f"Query: {query}\n")

        try:
            result = self.pubmed.run(query)
            print("✅ PubMed search succeeded!")
            print("\nResult:")
            print(result)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ PubMed search failed: {e}")
            return {"success": False, "error": str(e)}

    def test_semantic_scholar(self, query: str) -> Dict[str, Any]:
        """Test Semantic Scholar search."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing Semantic Scholar")
        print(f"{'='*80}")
        print(f"Query: {query}\n")

        try:
            result = self.semantic_scholar.run(query)
            print("✅ Semantic Scholar search succeeded!")
            print("\nResult:")
            print(result)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ Semantic Scholar search failed: {e}")
            return {"success": False, "error": str(e)}

    def test_yahoo_finance(self, query: str) -> Dict[str, Any]:
        """Test Yahoo Finance News."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing Yahoo Finance News")
        print(f"{'='*80}")
        print(f"Query: {query}\n")

        try:
            result = self.yahoo_finance.run(query)
            print("✅ Yahoo Finance News succeeded!")
            print("\nResult:")
            print(result)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ Yahoo Finance News failed: {e}")
            return {"success": False, "error": str(e)}

    def test_google_finance(self, query: str) -> Dict[str, Any]:
        """Test Google Finance."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing Google Finance")
        print(f"{'='*80}")
        print(f"Query: {query}\n")

        try:
            result = self.google_finance.run(query)
            print("✅ Google Finance succeeded!")
            print("\nResult:")
            print(result)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ Google Finance failed: {e}")
            return {"success": False, "error": str(e)}

    def test_google_trends(self, query: str) -> Dict[str, Any]:
        """Test Google Trends."""
        print(f"\n{'='*80}")
        print(f"🔍 Testing Google Trends")
        print(f"{'='*80}")
        print(f"Query: {query}\n")

        try:
            result = self.google_trends.run(query)
            print("✅ Google Trends succeeded!")
            print("\nResult:")
            print(result)
            return {"success": True, "result": result}
        except Exception as e:
            print(f"❌ Google Trends failed: {e}")
            return {"success": False, "error": str(e)}

    def run_all_tests(self, query_type: str = "topics") -> Dict[str, Any]:
        """Run all available tests with a default biotech query."""
        query = DEFAULT_BIOTECH_QUERIES.get(query_type, DEFAULT_BIOTECH_QUERIES["topics"])
        
        print(f"\n{'#'*80}")
        print(f"# Running All Tool Tests")
        print(f"# Query Type: {query_type}")
        print(f"# Query: {query}")
        print(f"{'#'*80}\n")

        results = {}

        # Search tools
        results["exa_search"] = self.test_exa_search(query)
        results["serper"] = self.test_serper(query)
        results["duckduckgo"] = self.test_duckduckgo(query)
        results["duckduckgo_results"] = self.test_duckduckgo_results(query)

        # Academic tools
        results["pubmed"] = self.test_pubmed(query)
        results["semantic_scholar"] = self.test_semantic_scholar(query)

        # Finance tools
        results["yahoo_finance"] = self.test_yahoo_finance(query)
        results["google_finance"] = self.test_google_finance(query)
        results["google_trends"] = self.test_google_trends(query)

        # Summary
        print(f"\n{'#'*80}")
        print("# Test Summary")
        print(f"{'#'*80}")
        for tool_name, result in results.items():
            status = "✅" if result.get("success") else "❌"
            print(f"{status} {tool_name}")

        return results


def main():
    """Main entry point for the test suite."""
    parser = argparse.ArgumentParser(
        description="Test suite for research agent search tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests with default biotech query
  uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --all

  # Run all tests with a specific query type
  uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --all --query-type people

  # Test a specific tool
  uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --tool exa --query "CRISPR gene editing"

  # Test with biotech company
  uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --tool serper --query "BioNTech mRNA technology"

  # Test Exa Find Similar
  uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --tool exa_similar --url "https://www.biontech.com"

  # List available tools
  uv run python -m research_agent.human_upgrade.tools.integrations.tool_tests --list
        """
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all available tool tests"
    )
    parser.add_argument(
        "--tool",
        type=str,
        choices=["exa", "exa_similar", "serper", "duckduckgo", "duckduckgo_results",
                 "pubmed", "semantic_scholar", "yahoo_finance", "google_finance", "google_trends"],
        help="Run a specific tool test"
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Custom query to use for testing"
    )
    parser.add_argument(
        "--query-type",
        type=str,
        choices=["people", "products", "topics", "companies", "research"],
        default="topics",
        help="Type of biotech query to use (default: topics)"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="URL for exa_similar tool"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available tools"
    )

    args = parser.parse_args()

    # List tools
    if args.list:
        print("\nAvailable Tools:")
        print("  Search Tools:")
        print("    - exa              : Exa neural search")
        print("    - exa_similar      : Exa find similar pages")
        print("    - serper           : Google Serper search")
        print("    - duckduckgo       : DuckDuckGo search")
        print("    - duckduckgo_results: DuckDuckGo structured results")
        print("  Academic Tools:")
        print("    - pubmed           : PubMed research papers")
        print("    - semantic_scholar : Semantic Scholar papers")
        print("  Finance Tools:")
        print("    - yahoo_finance    : Yahoo Finance news")
        print("    - google_finance   : Google Finance data")
        print("    - google_trends    : Google Trends data")
        print("\nQuery Types:")
        for qtype, example in DEFAULT_BIOTECH_QUERIES.items():
            print(f"    - {qtype:12} : {example}")
        return

    # Initialize test suite
    suite = ToolTestSuite()

    # Run all tests
    if args.all:
        suite.run_all_tests(query_type=args.query_type)
        return

    # Run specific tool
    if args.tool:
        query = args.query or DEFAULT_BIOTECH_QUERIES.get(args.query_type, DEFAULT_BIOTECH_QUERIES["topics"])

        tool_map = {
            "exa": suite.test_exa_search,
            "exa_similar": suite.test_exa_find_similar,
            "serper": suite.test_serper,
            "duckduckgo": suite.test_duckduckgo,
            "duckduckgo_results": suite.test_duckduckgo_results,
            "pubmed": suite.test_pubmed,
            "semantic_scholar": suite.test_semantic_scholar,
            "yahoo_finance": suite.test_yahoo_finance,
            "google_finance": suite.test_google_finance,
            "google_trends": suite.test_google_trends,
        }

        test_func = tool_map.get(args.tool)
        if not test_func:
            print(f"❌ Unknown tool: {args.tool}")
            return

        # Special handling for exa_similar which needs a URL
        if args.tool == "exa_similar":
            url = args.url or "https://www.onethousandroads.com"
            test_func(url)
        else:
            test_func(query)
        return

    # No arguments provided, show help
    parser.print_help()


if __name__ == "__main__":
    main()




