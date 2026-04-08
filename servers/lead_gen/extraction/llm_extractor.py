"""
LLM-based entity extraction using structured output.
Replaces BERT NER — zero training data needed, handles edge cases better.
Uses the same with_structured_output() pattern as the email server.
"""
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from servers.lead_gen.models import (
    LeadSearchInput, PageContent, ExtractedEntity, ExtractionResult
)
from servers.lead_gen.config import LLM_MODEL, LLM_TEMPERATURE, OPENAI_API_KEY

import os
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# LLM with structured output — guarantees valid JSON matching our schema
_extractor_llm = ChatOpenAI(
    model=LLM_MODEL,
    temperature=LLM_TEMPERATURE,
).with_structured_output(ExtractionResult)

EXTRACTION_PROMPT = PromptTemplate(
    input_variables=["page_text", "page_url", "target_profile"],
    template="""You are an expert B2B lead extraction system.

Analyze the following web page content and extract ALL people and their professional details.

TARGET PROFILE (what the user is looking for):
{target_profile}

PAGE URL: {page_url}

PAGE CONTENT:
{page_text}

INSTRUCTIONS:
1. Extract every person mentioned with professional context
2. For each person, capture: name, job title, company, industry, location, email, LinkedIn URL, phone
3. Extract relationships (e.g., "Reports to CEO John Doe", "Co-founded with Jane Smith")
4. Extract recent activity or news mentions (e.g., "Published article on X", "Company raised $Y")
5. If information is not available, leave the field as null
6. Only extract real people — skip fictional examples, testimonials without full context, or generic mentions
7. Be precise — do not guess or fabricate information

Return ALL extracted entities, even if they don't perfectly match the target profile.
The scoring step will handle relevance filtering."""
)


async def extract_entities(
    page: PageContent,
    query: LeadSearchInput,
    source_name: str = "web_crawl",
) -> list[ExtractedEntity]:
    """
    Extract structured entities from a rendered page using LLM.
    Handles chunking for long pages.
    """
    if not page.text or len(page.text.strip()) < 50:
        return []

    target_profile = _build_target_profile(query)

    try:
        # For very long pages, chunk and extract from each chunk
        text_chunks = _chunk_text(page.text, max_chars=8000)
        all_entities: list[ExtractedEntity] = []

        for chunk in text_chunks:
            prompt = EXTRACTION_PROMPT.format(
                page_text=chunk,
                page_url=page.url,
                target_profile=target_profile,
            )

            result: ExtractionResult = await _extractor_llm.ainvoke(prompt)

            for entity in result.entities:
                # Tag the source
                entity.source_url = page.url
                entity.source_name = source_name
                all_entities.append(entity)

        print(f"[Extractor] Extracted {len(all_entities)} entities from {page.url[:60]}")
        return all_entities

    except Exception as e:
        print(f"[Extractor] Error extracting from {page.url}: {e}")
        return []


def extract_from_hunter_data(raw_data: dict, source_url: str = "") -> ExtractedEntity:
    """Convert Hunter.io raw_data directly into an ExtractedEntity (no LLM needed)."""
    first = raw_data.get("first_name", "")
    last = raw_data.get("last_name", "")
    return ExtractedEntity(
        name=f"{first} {last}".strip() or "Unknown",
        title=raw_data.get("position", None),
        company=raw_data.get("company", None),
        email=raw_data.get("email", None),
        linkedin_url=raw_data.get("linkedin", None) or None,
        phone=raw_data.get("phone_number", None) or None,
        source_url=source_url,
        source_name="hunter",
    )


def extract_from_proxycurl_data(raw_data: dict, source_url: str = "") -> ExtractedEntity:
    """Convert Proxycurl raw_data directly into an ExtractedEntity (no LLM needed)."""
    first = raw_data.get("first_name", "")
    last = raw_data.get("last_name", "")
    return ExtractedEntity(
        name=f"{first} {last}".strip() or "Unknown",
        title=raw_data.get("current_role", None) or raw_data.get("headline", None),
        company=raw_data.get("current_company", None),
        location=f"{raw_data.get('city', '')}, {raw_data.get('country', '')}".strip(", ") or None,
        linkedin_url=raw_data.get("linkedin_url", None),
        source_url=source_url,
        source_name="proxycurl",
    )


def _build_target_profile(query: LeadSearchInput) -> str:
    """Build a human-readable target profile string for the LLM prompt."""
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


def _chunk_text(text: str, max_chars: int = 8000) -> list[str]:
    """Split long text into chunks, trying to break at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break

        # Try to break at a paragraph boundary
        break_point = text.rfind("\n\n", 0, max_chars)
        if break_point < max_chars // 2:
            # No good paragraph break — break at sentence
            break_point = text.rfind(". ", 0, max_chars)
        if break_point < max_chars // 2:
            # No good sentence break either — hard break
            break_point = max_chars

        chunks.append(text[:break_point])
        text = text[break_point:].lstrip()

    return chunks
