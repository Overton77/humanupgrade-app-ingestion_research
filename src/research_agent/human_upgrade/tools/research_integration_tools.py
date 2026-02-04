"""
Research Integration Tools

This module provides instantiated search, academic, and finance tools for the research agent.
All tools are initialized from environment variables and can be imported directly.

Usage:
    from research_agent.human_upgrade.tools.research_integration_tools import (
        exa_search,
        serper_search,
        duckduckgo_search,
        pubmed,
        semantic_scholar,
        yahoo_finance,
        google_finance,
        google_trends,
    )
"""

import os
from typing import Optional
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

# Load environment variables
load_dotenv()

# Set SERPAPI_API_KEY from SERP_API_KEY if needed
if os.getenv("SERP_API_KEY") and not os.getenv("SERPAPI_API_KEY"):
    os.environ["SERPAPI_API_KEY"] = os.getenv("SERP_API_KEY")

# Get API keys
EXA_API_KEY = os.getenv("EXA_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")

# ============================================================================
# Exa Tools
# ============================================================================

exa_search: Optional[ExaSearchResults] = None
exa_find_similar: Optional[ExaFindSimilarResults] = None

if EXA_API_KEY:
    exa_search = ExaSearchResults(exa_api_key=EXA_API_KEY)
    exa_find_similar = ExaFindSimilarResults(exa_api_key=EXA_API_KEY)

# ============================================================================
# Google Serper
# ============================================================================

serper_search: Optional[GoogleSerperAPIWrapper] = None

if SERPER_API_KEY:
    serper_search = GoogleSerperAPIWrapper(serper_api_key=SERPER_API_KEY)

# ============================================================================
# DuckDuckGo Tools
# ============================================================================

# DuckDuckGo doesn't require API keys
duckduckgo_search = DuckDuckGoSearchRun()
duckduckgo_search_results = DuckDuckGoSearchResults()

# ============================================================================
# Academic/Scholarly Tools
# ============================================================================

# These tools don't require API keys
pubmed = PubmedQueryRun()
semantic_scholar = SemanticScholarQueryRun()

# ============================================================================
# Finance Tools
# ============================================================================

# These tools don't require API keys
yahoo_finance = YahooFinanceNewsTool()
google_finance = GoogleFinanceQueryRun(api_wrapper=GoogleFinanceAPIWrapper())
google_trends = GoogleTrendsQueryRun(api_wrapper=GoogleTrendsAPIWrapper())

# ============================================================================
# Tool Availability Checker
# ============================================================================

def get_available_tools() -> dict:
    """
    Returns a dictionary indicating which tools are available.
    
    Returns:
        dict: Dictionary with tool names as keys and availability (bool) as values
    """
    return {
        "exa_search": exa_search is not None,
        "exa_find_similar": exa_find_similar is not None,
        "serper_search": serper_search is not None,
        "duckduckgo_search": duckduckgo_search is not None,
        "duckduckgo_search_results": duckduckgo_search_results is not None,
        "pubmed": pubmed is not None,
        "semantic_scholar": semantic_scholar is not None,
        "yahoo_finance": yahoo_finance is not None,
        "google_finance": google_finance is not None,
        "google_trends": google_trends is not None,
    }
