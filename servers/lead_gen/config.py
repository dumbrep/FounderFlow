"""
Configuration management for Lead Generation MCP Server.
Loads API keys from environment and defines pipeline settings.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── API Keys ────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")
PROXYCURL_API_KEY = os.getenv("PROXYCURL_API_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

# ─── LLM Settings ────────────────────────────────────────────────────────────
LLM_MODEL = os.getenv("LEAD_GEN_LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = 0

# ─── Crawler Settings ────────────────────────────────────────────────────────
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", "15"))
MAX_CRAWL_DEPTH = int(os.getenv("MAX_CRAWL_DEPTH", "2"))
CRAWL_DELAY_SECONDS = float(os.getenv("CRAWL_DELAY_SECONDS", "1.0"))
PAGE_TIMEOUT_MS = int(os.getenv("PAGE_TIMEOUT_MS", "15000"))

# ─── Deduplication Settings ──────────────────────────────────────────────────
DEDUP_SIMILARITY_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", "85"))

# ─── Search Settings ─────────────────────────────────────────────────────────
MAX_SEARCH_RESULTS_PER_SOURCE = int(os.getenv("MAX_RESULTS_PER_SOURCE", "10"))

# ─── Available Sources (auto-detected from API keys) ─────────────────────────
def get_available_sources() -> list[str]:
    """Return list of source names whose API keys are configured."""
    sources = []
    if SERPAPI_KEY:
        sources.append("google")
    if HUNTER_API_KEY:
        sources.append("hunter")
    if PROXYCURL_API_KEY:
        sources.append("proxycurl")
    if NEWSAPI_KEY:
        sources.append("newsapi")
    # Open web crawling is always available (no API key needed)
    sources.append("web_crawl")
    return sources
