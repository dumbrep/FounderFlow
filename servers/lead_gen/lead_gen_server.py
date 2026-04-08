"""
Lead Generation MCP Server — Entry Point.
Exposes 3 tools via FastMCP:
  1. searchLeads — Full pipeline: search → crawl → extract → score → dedup → summarize
  2. scoreLeadProfile — Score a single profile against target criteria
  3. getLeadReport — Get a previously generated report

This server runs on port 8006.
"""
import asyncio
import json
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

# Pipeline imports
from .config import get_available_sources
from .models import (
    LeadSearchInput, RawSearchResult, ExtractedEntity,
    ScoredLead, LeadReport, LeadReportEntry
)
from .search.google_search import GoogleSearchSource
from .search.hunter import HunterSource
from .search.news_api import NewsAPISource
from .search.proxycurl import ProxycurlSource
from .crawler.priority_crawler import PriorityCrawler
from .extraction.llm_extractor import (
    extract_entities, extract_from_hunter_data, extract_from_proxycurl_data
)
from .scoring.lead_scorer import score_leads_batch
from .dedup.entity_resolver import deduplicate_leads
from .report.summarizer import generate_report


# ─── MCP Server Setup ────────────────────────────────────────────────────────

mcp = FastMCP("Lead_Gen", port=8006)

# Data source registry — auto-discovers which sources are available
ALL_SOURCES = [
    GoogleSearchSource(),
    HunterSource(),
    NewsAPISource(),
    ProxycurlSource(),
]

# In-memory cache of last generated report (for getLeadReport)
_last_report: LeadReport | None = None


# ─── Tool Input Models ───────────────────────────────────────────────────────

class SearchLeadsArgs(BaseModel):
    keywords: list[str] | None = None
    industry: str | None = None
    persona: str | None = None
    company: str | None = None
    location: str | None = None


class ScoreProfileArgs(BaseModel):
    name: str
    title: str | None = None
    company: str | None = None
    industry: str | None = None
    location: str | None = None
    email: str | None = None
    target_keywords: list[str] | None = None
    target_industry: str | None = None
    target_persona: str | None = None


# ─── Tool 1: searchLeads (Full Pipeline) ─────────────────────────────────────

@mcp.tool(name="searchLeads")
async def search_leads(args: SearchLeadsArgs) -> str:
    """
    Search for B2B leads matching the target profile.
    Automatically searches ALL available data sources, extracts entities,
    scores them, deduplicates, and generates a ranked report with summaries.

    :param keywords: Search keywords like 'cloud infrastructure', 'DevOps'
    :param industry: Target industry like 'SaaS', 'FinTech'
    :param persona: Target persona/role like 'CTO', 'VP Engineering'
    :param company: Specific company name to research
    :param location: Geographic filter like 'San Francisco'
    """
    global _last_report

    query = LeadSearchInput(
        keywords=args.keywords or [],
        industry=args.industry,
        persona=args.persona,
        company=args.company,
        location=args.location,
    )

    print(f"\n{'='*60}")
    print(f"[LeadGen] Starting search: {query.to_search_query()}")
    print(f"{'='*60}\n")

    # ── Stage 2: Parallel Search across all available sources ──
    available = [src for src in ALL_SOURCES if src.is_available()]
    source_names = [src.name for src in available]
    print(f"[LeadGen] Searching {len(available)} sources: {source_names}")

    search_tasks = [src.search(query) for src in available]
    search_results_lists = await asyncio.gather(*search_tasks, return_exceptions=True)

    all_raw_results: list[RawSearchResult] = []
    for i, result in enumerate(search_results_lists):
        if isinstance(result, list):
            all_raw_results.extend(result)
        else:
            print(f"[LeadGen] Source {source_names[i]} failed: {result}")

    print(f"[LeadGen] Total raw results: {len(all_raw_results)}")

    if not all_raw_results:
        return json.dumps({
            "success": False,
            "message": "No results found from any source. Check API keys and try different search terms.",
            "sources_searched": source_names,
        })

    # ── Stage 3-4: Crawl discovered URLs + render pages ──
    # Collect URLs from search results for crawling
    crawl_urls = [r.url for r in all_raw_results if r.url and r.source == "google"]
    
    crawler = PriorityCrawler(query)
    crawled_pages = await crawler.crawl(crawl_urls[:20])  # Limit seed URLs

    # ── Stage 5: Extract entities ──
    all_entities: list[ExtractedEntity] = []

    # Extract from crawled pages using LLM
    for page in crawled_pages:
        entities = await extract_entities(page, query, source_name="web_crawl")
        all_entities.extend(entities)

    # Direct extraction from structured API data (no LLM needed)
    for result in all_raw_results:
        if result.source == "hunter" and result.raw_data.get("email"):
            entity = extract_from_hunter_data(result.raw_data, result.url)
            all_entities.append(entity)
        elif result.source == "proxycurl" and result.raw_data.get("first_name"):
            entity = extract_from_proxycurl_data(result.raw_data, result.url)
            all_entities.append(entity)

    # Also extract from news snippets (use LLM on concatenated snippets)
    news_results = [r for r in all_raw_results if r.source == "newsapi"]
    if news_results:
        from .models import PageContent
        news_text = "\n\n".join(
            f"Title: {r.title}\nSource: {r.raw_data.get('source_name', '')}\n"
            f"Date: {r.raw_data.get('published_at', '')}\n{r.snippet}"
            for r in news_results
        )
        news_page = PageContent(
            url="news_aggregation",
            title="News Results",
            text=news_text,
        )
        news_entities = await extract_entities(news_page, query, source_name="newsapi")
        all_entities.extend(news_entities)

    print(f"[LeadGen] Total extracted entities: {len(all_entities)}")

    if not all_entities:
        return json.dumps({
            "success": True,
            "message": "Search completed but no lead entities could be extracted. Try broader keywords.",
            "sources_searched": source_names,
            "pages_crawled": crawler.pages_crawled,
        })

    # ── Stage 6: Score leads ──
    scored_leads = await score_leads_batch(all_entities, query)

    # ── Stage 7: Deduplicate ──
    unique_leads = deduplicate_leads(scored_leads)

    # ── Stage 8-9: Structured JSON + LLM Summarizer ──
    # Only summarize top leads (max 20) to save API costs
    top_leads = unique_leads[:20]
    report = await generate_report(top_leads, query, total_sources=len(available))

    # Cache the report
    _last_report = report

    # ── Stage 10: Return the Lead Report ──
    # Format as a readable JSON string for the LLM agent to present
    report_dict = report.model_dump()
    return json.dumps({
        "success": True,
        "message": f"Found {report.total_leads_found} leads from {report.total_sources_searched} sources",
        "report": report_dict,
    }, indent=2, default=str)


# ─── Tool 2: scoreLeadProfile ────────────────────────────────────────────────

@mcp.tool(name="scoreLeadProfile")
async def score_lead_profile(args: ScoreProfileArgs) -> str:
    """
    Score a single lead profile against target criteria.
    Useful for quickly evaluating a specific person without doing full search.

    :param name: Person's name
    :param title: Job title
    :param company: Company name
    :param industry: Industry
    :param location: Location
    :param email: Email address
    :param target_keywords: Keywords to match against
    :param target_industry: Target industry for scoring
    :param target_persona: Target persona/role for scoring
    """
    from .scoring.lead_scorer import score_lead

    entity = ExtractedEntity(
        name=args.name,
        title=args.title,
        company=args.company,
        industry=args.industry,
        location=args.location,
        email=args.email,
        source_name="manual_input",
    )

    query = LeadSearchInput(
        keywords=args.target_keywords or [],
        industry=args.target_industry,
        persona=args.target_persona,
    )

    scored = await score_lead(entity, query)

    return json.dumps({
        "success": True,
        "name": args.name,
        "score": scored.score.score,
        "reasoning": scored.score.reasoning,
        "industry_match": scored.score.industry_match,
        "persona_match": scored.score.persona_match,
        "keyword_matches": scored.score.keyword_matches,
    }, indent=2)


# ─── Tool 3: getLeadReport ───────────────────────────────────────────────────

@mcp.tool(name="getLeadReport")
async def get_lead_report() -> str:
    """
    Retrieve the most recently generated lead report.
    Call searchLeads first to generate a report.
    """
    if _last_report is None:
        return json.dumps({
            "success": False,
            "message": "No report available. Run searchLeads first.",
        })

    return json.dumps({
        "success": True,
        "report": _last_report.model_dump(),
    }, indent=2, default=str)


# ─── Server Entry Point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    available = get_available_sources()
    print(f"\n{'='*60}")
    print(f"  Lead Generation MCP Server")
    print(f"  Port: 8006")
    print(f"  Available sources: {available}")
    print(f"{'='*60}\n")

    mcp.run(transport="streamable-http")
