"""
LLM-based lead scoring.
Replaces Siamese Network + XGBoost with a prompt-based scorer.
No training data needed — works immediately with any target profile.
"""
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from ..models import (
    LeadSearchInput, ExtractedEntity, LeadScore, ScoredLead
)
from ..config import LLM_MODEL, LLM_TEMPERATURE, OPENAI_API_KEY

import os
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

_scorer_llm = ChatOpenAI(
    model=LLM_MODEL,
    temperature=LLM_TEMPERATURE,
).with_structured_output(LeadScore)

SCORING_PROMPT = PromptTemplate(
    input_variables=["lead_data", "target_profile"],
    template="""You are an expert B2B lead scoring system.

Score the following lead against the target profile on a scale of 0-100.

TARGET PROFILE:
{target_profile}

LEAD DATA:
{lead_data}

SCORING CRITERIA:
- Industry match (0-25 points): Does the lead's industry match the target?
- Persona match (0-25 points): Does the lead's role/title match the target persona?
- Keyword relevance (0-25 points): How many target keywords relate to this lead?
- Signal quality (0-25 points): Quality of data (has email? recent activity? seniority?)

SCORING GUIDELINES:
- 85-100: Perfect match — high seniority, exact industry, recent activity, contact info
- 70-84: Strong match — good industry/role fit, some contact info
- 50-69: Moderate match — partial overlap, might be worth exploring
- 25-49: Weak match — tangential connection at best
- 0-24: No match — wrong industry, wrong role, or insufficient data

Be precise and honest. A score of 90+ should mean "this is exactly who we're looking for."
Explain your reasoning clearly."""
)


async def score_lead(
    entity: ExtractedEntity,
    query: LeadSearchInput,
    sources: list[str] | None = None,
) -> ScoredLead:
    """Score a single extracted entity against the target profile."""
    target_profile = _build_target_string(query)
    lead_data = _build_lead_string(entity)

    try:
        prompt = SCORING_PROMPT.format(
            lead_data=lead_data,
            target_profile=target_profile,
        )

        score: LeadScore = await _scorer_llm.ainvoke(prompt)

        return ScoredLead(
            entity=entity,
            score=score,
            sources=sources or [entity.source_name],
        )

    except Exception as e:
        print(f"[Scorer] Error scoring {entity.name}: {e}")
        # Return a zero-score lead on error
        return ScoredLead(
            entity=entity,
            score=LeadScore(
                score=0,
                reasoning=f"Scoring failed: {str(e)}",
            ),
            sources=sources or [entity.source_name],
        )


async def score_leads_batch(
    entities: list[ExtractedEntity],
    query: LeadSearchInput,
) -> list[ScoredLead]:
    """Score multiple leads. Uses concurrent calls for speed."""
    import asyncio

    tasks = [score_lead(entity, query) for entity in entities]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scored = []
    for r in results:
        if isinstance(r, ScoredLead):
            scored.append(r)
        else:
            print(f"[Scorer] Batch scoring error: {r}")

    # Sort by score descending
    scored.sort(key=lambda x: x.score.score, reverse=True)

    print(f"[Scorer] Scored {len(scored)} leads. "
          f"Top score: {scored[0].score.score if scored else 'N/A'}")

    return scored


def _build_target_string(query: LeadSearchInput) -> str:
    parts = []
    if query.keywords:
        parts.append(f"Keywords: {', '.join(query.keywords)}")
    if query.industry:
        parts.append(f"Industry: {query.industry}")
    if query.persona:
        parts.append(f"Persona: {query.persona}")
    if query.company:
        parts.append(f"Company: {query.company}")
    if query.location:
        parts.append(f"Location: {query.location}")
    return "\n".join(parts) if parts else "General B2B lead search"


def _build_lead_string(entity: ExtractedEntity) -> str:
    parts = [f"Name: {entity.name}"]
    if entity.title:
        parts.append(f"Title: {entity.title}")
    if entity.company:
        parts.append(f"Company: {entity.company}")
    if entity.industry:
        parts.append(f"Industry: {entity.industry}")
    if entity.location:
        parts.append(f"Location: {entity.location}")
    if entity.email:
        parts.append(f"Email: {entity.email}")
    if entity.linkedin_url:
        parts.append(f"LinkedIn: {entity.linkedin_url}")
    if entity.relations:
        parts.append(f"Relations: {', '.join(entity.relations)}")
    if entity.recent_activity:
        parts.append(f"Recent activity: {', '.join(entity.recent_activity)}")
    return "\n".join(parts)
