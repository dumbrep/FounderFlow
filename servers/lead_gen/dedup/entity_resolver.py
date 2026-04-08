import re
from rapidfuzz import fuzz
from servers.lead_gen.models import ExtractedEntity, ScoredLead
from servers.lead_gen.config import DEDUP_SIMILARITY_THRESHOLD


def deduplicate_leads(scored_leads: list[ScoredLead]) -> list[ScoredLead]:
    """
    Deduplicate a list of scored leads using multi-factor identity resolution.
    When duplicates are found, merge them into a single record.
    """
    if not scored_leads:
        return []

    # Sort by score descending so the best-scored version is the base
    sorted_leads = sorted(scored_leads, key=lambda x: x.score.score, reverse=True)

    unique_leads: list[ScoredLead] = []
    merged_indices: set[int] = set()

    for i, lead_a in enumerate(sorted_leads):
        if i in merged_indices:
            continue

        # Find all duplicates of this lead
        duplicates: list[ScoredLead] = [lead_a]

        for j in range(i + 1, len(sorted_leads)):
            if j in merged_indices:
                continue

            lead_b = sorted_leads[j]
            if _are_duplicates(lead_a.entity, lead_b.entity):
                duplicates.append(lead_b)
                merged_indices.add(j)

        # Merge all duplicates into a single golden record
        if len(duplicates) > 1:
            merged = _merge_leads(duplicates)
            unique_leads.append(merged)
            print(f"[Dedup] Merged {len(duplicates)} records for: {merged.entity.name}")
        else:
            unique_leads.append(lead_a)

    print(f"[Dedup] {len(scored_leads)} leads → {len(unique_leads)} unique leads "
          f"({len(scored_leads) - len(unique_leads)} duplicates merged)")

    return unique_leads


def _are_duplicates(a: ExtractedEntity, b: ExtractedEntity) -> bool:
    """
    Determine if two entities refer to the same person/company.
    Uses definitive identifiers (Email, Phone, LinkedIn) then fuzzy fallbacks.
    """
    # 1. Exact email match (case-insensitive, stripped)
    if a.email and b.email:
        if a.email.lower().strip() == b.email.lower().strip():
            return True

    # 2. Exact Phone match (digit-only normalization)
    p_a = _normalize_phone(a.phone)
    p_b = _normalize_phone(b.phone)
    if p_a and p_b and p_a == p_b:
        return True

    # 3. Exact LinkedIn URL match
    if a.linkedin_url and b.linkedin_url:
        if _normalize_linkedin(a.linkedin_url) == _normalize_linkedin(b.linkedin_url):
            return True

    # 4. Fuzzy name matching on cleaned names
    n_a = _clean_business_name(a.name)
    n_b = _clean_business_name(b.name)
    
    # Simple membership check (e.g. "Activebit" in "Pune SEO Experts (Activebit)")
    if (len(n_a) > 5 and len(n_b) > 5) and (n_a in n_b or n_b in n_a):
        return True

    name_sim = fuzz.token_sort_ratio(n_a, n_b)

    # Company matching (if lead names match and they are associated with similar companies)
    company_sim = 0
    if a.company and b.company:
        company_sim = fuzz.partial_ratio(
            _clean_business_name(a.company), 
            _clean_business_name(b.company)
        )

    # If the base names are very similar, or combined score is high enough
    if name_sim >= DEDUP_SIMILARITY_THRESHOLD:
        if not a.company or not b.company:
            return name_sim >= 90
        else:
            combined = (name_sim * 0.6) + (company_sim * 0.4)
            return combined >= DEDUP_SIMILARITY_THRESHOLD

    return False


def _merge_leads(duplicates: list[ScoredLead]) -> ScoredLead:
    """Merge multiple leads into a single Golden Record."""
    # Base starts as highest-scored lead
    base = duplicates[0]
    merged_entity = base.entity.model_copy()
    merged_sources = set(base.sources)

    # Use the longest name as the canonical name (often most descriptive)
    all_names = [d.entity.name for d in duplicates]
    merged_entity.name = max(all_names, key=len)

    for dup in duplicates[1:]:
        ent = dup.entity
        merged_sources.update(dup.sources)

        # Fill in missing fields
        if not merged_entity.title and ent.title:
            merged_entity.title = ent.title
        if not merged_entity.company and ent.company:
            merged_entity.company = ent.company
        if not merged_entity.industry and ent.industry:
            merged_entity.industry = ent.industry
        if not merged_entity.location and ent.location:
            merged_entity.location = ent.location
        if not merged_entity.email and ent.email:
            merged_entity.email = ent.email
        if not merged_entity.linkedin_url and ent.linkedin_url:
            merged_entity.linkedin_url = ent.linkedin_url
        if not merged_entity.phone and ent.phone:
            merged_entity.phone = ent.phone

        # Merge relations/activity unique items
        for rel in ent.relations:
            if rel not in merged_entity.relations:
                merged_entity.relations.append(rel)
        for act in ent.recent_activity:
            if act not in merged_entity.recent_activity:
                merged_entity.recent_activity.append(act)

    return ScoredLead(
        entity=merged_entity,
        score=base.score,
        sources=list(merged_sources),
    )


def _normalize_phone(phone: str | None) -> str:
    """Strip all non-digits from a phone number."""
    if not phone: return ""
    return re.sub(r"\D", "", phone)


def _clean_business_name(name: str | None) -> str:
    """Normalize and clean commercial suffixes for better comparison."""
    if not name: return ""
    name = name.lower().strip()
    # Remove business suffixes and common noise
    noise = [
        "technologies", "technology", "solutions", "pvt", "ltd", "private", "limited",
        "services", "systems", "experts", "llp", "inc", "corp", "software"
    ]
    for n in noise:
        name = re.sub(fr"\b{n}\b", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _normalize_linkedin(url: str) -> str:
    """Normalize a LinkedIn URL for comparison."""
    url = url.lower().strip().rstrip("/")
    url = url.replace("https://", "").replace("http://", "")
    url = url.replace("www.", "")
    return url
