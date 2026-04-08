"""
Pydantic models for the Lead Generation pipeline.
These define the data contracts between every stage of the pipeline.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


# ─── Stage 1: User Input ─────────────────────────────────────────────────────

class LeadSearchInput(BaseModel):
    """What the user provides to start a search."""
    keywords: list[str] = Field(default_factory=list, description="Search keywords like 'cloud infrastructure', 'DevOps'")
    industry: Optional[str] = Field(default=None, description="Target industry like 'SaaS', 'FinTech'")
    persona: Optional[str] = Field(default=None, description="Target persona like 'CTO', 'VP Engineering'")
    company: Optional[str] = Field(default=None, description="Specific company name to research")
    location: Optional[str] = Field(default=None, description="Geographic filter like 'San Francisco'")

    def to_search_query(self) -> str:
        """Build a natural-language search string from all provided fields."""
        parts = []
        if self.keywords:
            parts.append(" ".join(self.keywords))
        if self.industry:
            parts.append(self.industry)
        if self.persona:
            parts.append(self.persona)
        if self.company:
            parts.append(self.company)
        if self.location:
            parts.append(self.location)
        return " ".join(parts)


# ─── Stage 2: Raw Search Results ─────────────────────────────────────────────

class RawSearchResult(BaseModel):
    """A single result returned by any data source adapter."""
    source: str = Field(description="Which source produced this: 'google', 'hunter', 'newsapi', etc.")
    url: str = Field(default="", description="URL of the result page")
    title: str = Field(default="", description="Title / headline")
    snippet: str = Field(default="", description="Short text preview")
    raw_data: dict = Field(default_factory=dict, description="Any extra source-specific data")


# ─── Stage 4: Rendered Page Content ──────────────────────────────────────────

class PageContent(BaseModel):
    """Clean text extracted from a rendered web page."""
    url: str
    title: str = ""
    text: str = ""
    meta_description: str = ""
    links: list[str] = Field(default_factory=list, description="Outgoing links found on page")


# ─── Stage 5: Extracted Entity ───────────────────────────────────────────────

class ExtractedEntity(BaseModel):
    """A single person/company entity extracted by the LLM."""
    name: str = Field(description="Person's full name")
    title: Optional[str] = Field(default=None, description="Job title like 'VP of Engineering'")
    company: Optional[str] = Field(default=None, description="Company name")
    industry: Optional[str] = Field(default=None, description="Industry if mentioned")
    location: Optional[str] = Field(default=None, description="Location if mentioned")
    email: Optional[str] = Field(default=None, description="Email address if found")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn profile URL if found")
    phone: Optional[str] = Field(default=None, description="Phone number if found")
    relations: list[str] = Field(default_factory=list, description="Relationships like 'Reports to CEO John Doe'")
    recent_activity: list[str] = Field(default_factory=list, description="Recent mentions, posts, news")
    source_url: str = Field(default="", description="The URL this entity was extracted from")
    source_name: str = Field(default="", description="Which source adapter found this")


class ExtractionResult(BaseModel):
    """LLM extraction output — may contain multiple entities from one page."""
    entities: list[ExtractedEntity] = Field(default_factory=list)


# ─── Stage 6: Scored Lead ────────────────────────────────────────────────────

class LeadScore(BaseModel):
    """Score assigned by the LLM scorer."""
    score: int = Field(ge=0, le=100, description="Lead quality score 0-100")
    reasoning: str = Field(description="Why this score was given")
    industry_match: bool = Field(default=False)
    persona_match: bool = Field(default=False)
    keyword_matches: list[str] = Field(default_factory=list)


class ScoredLead(BaseModel):
    """An extracted entity with its score attached."""
    entity: ExtractedEntity
    score: LeadScore
    sources: list[str] = Field(default_factory=list, description="All sources that mentioned this lead")


# ─── Stage 9-10: Final Lead Report ───────────────────────────────────────────

class LeadSummary(BaseModel):
    """LLM-generated summary for a single lead."""
    executive_summary: str = Field(description="2-3 sentence summary")
    match_analysis: str = Field(description="Why they are a strong/weak match")
    approach_angle: str = Field(description="Best angle to approach them")
    red_flags: str = Field(description="Red flags or missing information")


class LeadReportEntry(BaseModel):
    """A single lead in the final report."""
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None
    lead_score: int
    score_reasoning: str
    relations: list[str] = Field(default_factory=list)
    recent_activity: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    summary: LeadSummary


class LeadReport(BaseModel):
    """The final output — a ranked list of leads with summaries."""
    query: LeadSearchInput
    total_leads_found: int
    total_sources_searched: int
    leads: list[LeadReportEntry] = Field(default_factory=list)
