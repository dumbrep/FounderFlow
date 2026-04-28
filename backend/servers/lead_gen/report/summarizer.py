"""
LLM Summarizer — generates human-readable lead reports.
Takes structured JSON per lead and produces actionable summaries.
"""
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from ..models import (
    LeadSearchInput, ScoredLead, LeadSummary,
    LeadReportEntry, LeadReport
)
from .templates import LEAD_SUMMARY_TEMPLATE
from ..config import LLM_MODEL, LLM_TEMPERATURE, OPENAI_API_KEY

import os
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

_summarizer_llm = ChatOpenAI(
    model=LLM_MODEL,
    temperature=0.3,  # Slightly creative for natural summaries
).with_structured_output(LeadSummary)

_summary_prompt = PromptTemplate(
    input_variables=["lead_json", "target_profile"],
    template=LEAD_SUMMARY_TEMPLATE,
)


async def summarize_lead(
    scored_lead: ScoredLead,
    query: LeadSearchInput,
) -> LeadReportEntry:
    """Generate a full report entry for a single scored lead."""
    entity = scored_lead.entity

    # Build the lead JSON for the prompt
    lead_json = json.dumps({
        "name": entity.name,
        "title": entity.title,
        "company": entity.company,
        "industry": entity.industry,
        "location": entity.location,
        "email": entity.email,
        "linkedin": entity.linkedin_url,
        "lead_score": scored_lead.score.score,
        "score_reasoning": scored_lead.score.reasoning,
        "relations": entity.relations,
        "recent_activity": entity.recent_activity,
        "sources": scored_lead.sources,
        "matched_keywords": scored_lead.score.keyword_matches,
    }, indent=2)

    target_profile = _build_target_profile(query)

    try:
        prompt = _summary_prompt.format(
            lead_json=lead_json,
            target_profile=target_profile,
        )

        summary: LeadSummary = await _summarizer_llm.ainvoke(prompt)

    except Exception as e:
        print(f"[Summarizer] Error summarizing {entity.name}: {e}")
        summary = LeadSummary(
            executive_summary=f"Lead: {entity.name}, {entity.title or 'Unknown role'} at {entity.company or 'Unknown company'}",
            match_analysis=scored_lead.score.reasoning,
            approach_angle="Insufficient data for recommendation.",
            red_flags="Summary generation failed — review raw data.",
        )

    return LeadReportEntry(
        name=entity.name,
        title=entity.title,
        company=entity.company,
        industry=entity.industry,
        location=entity.location,
        email=entity.email,
        linkedin_url=entity.linkedin_url,
        phone=entity.phone,
        lead_score=scored_lead.score.score,
        score_reasoning=scored_lead.score.reasoning,
        relations=entity.relations,
        recent_activity=entity.recent_activity,
        sources=scored_lead.sources,
        matched_keywords=scored_lead.score.keyword_matches,
        summary=summary,
    )


async def generate_report(
    scored_leads: list[ScoredLead],
    query: LeadSearchInput,
    total_sources: int,
) -> LeadReport:
    """Generate full lead report with summaries for all leads."""
    import asyncio

    # Batch summarized leads to avoid OpenAI TPM rate limits
    # (Typical 30k TPM limit for Tier 1 accounts)
    batch_size = 3
    all_entries = []
    
    for i in range(0, len(scored_leads), batch_size):
        batch = scored_leads[i : i + batch_size]
        print(f"[Summarizer] Processing batch {i//batch_size + 1}/{(len(scored_leads)-1)//batch_size + 1} ({len(batch)} leads)")
        
        tasks = [summarize_lead(lead, query) for lead in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for entry in batch_results:
            if isinstance(entry, LeadReportEntry):
                all_entries.append(entry)
            else:
                print(f"[Summarizer] Report entry error: {entry}")
        
        # Polite delay to avoid bursting over TPM limits
        if i + batch_size < len(scored_leads):
            await asyncio.sleep(1.5)

    # Sort by lead score descending
    all_entries.sort(key=lambda x: x.lead_score, reverse=True)

    report = LeadReport(
        query=query,
        total_leads_found=len(all_entries),
        total_sources_searched=total_sources,
        leads=all_entries,
    )

    print(f"[Summarizer] Generated report with {len(all_entries)} leads")
    return report


def _build_target_profile(query: LeadSearchInput) -> str:
    parts = []
    if query.keywords:
        parts.append(f"- Keywords: {', '.join(query.keywords)}")
    if query.industry:
        parts.append(f"- Industry: {query.industry}")
    if query.persona:
        parts.append(f"- Persona: {query.persona}")
    if query.company:
        parts.append(f"- Company: {query.company}")
    if query.location:
        parts.append(f"- Location: {query.location}")
    return "\n".join(parts) if parts else "General B2B lead search"
