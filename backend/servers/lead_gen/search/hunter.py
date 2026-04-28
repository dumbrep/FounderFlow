"""
Hunter.io adapter for email discovery.
Given a company domain or name, finds associated email addresses and people.
"""
import aiohttp
from .base import DataSource
from ..models import LeadSearchInput, RawSearchResult
from ..config import HUNTER_API_KEY, MAX_SEARCH_RESULTS_PER_SOURCE


class HunterSource(DataSource):
    name = "hunter"

    def is_available(self) -> bool:
        return bool(HUNTER_API_KEY)

    async def search(self, query: LeadSearchInput) -> list[RawSearchResult]:
        if not self.is_available():
            return []

        results: list[RawSearchResult] = []

        # Hunter.io works best with a company name or domain
        # We'll use the domain-search endpoint if company is provided,
        # otherwise use the email-finder endpoint with keywords
        if query.company:
            await self._search_by_company(query.company, results)
        
        # Also try keyword-based search by building a domain guess
        if query.keywords:
            search_term = query.to_search_query()
            await self._search_by_query(search_term, results)

        return results[:MAX_SEARCH_RESULTS_PER_SOURCE]

    async def _search_by_company(self, company: str, results: list[RawSearchResult]):
        """Use Hunter's domain-search to find emails for a company."""
        params = {
            "company": company,
            "api_key": HUNTER_API_KEY,
            "limit": MAX_SEARCH_RESULTS_PER_SOURCE,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.hunter.io/v2/domain-search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        print(f"[Hunter] domain-search returned {resp.status}")
                        return
                    data = await resp.json()

            domain_data = data.get("data", {})
            domain = domain_data.get("domain", "")
            org_name = domain_data.get("organization", company)

            for email_entry in domain_data.get("emails", []):
                first = email_entry.get("first_name", "")
                last = email_entry.get("last_name", "")
                full_name = f"{first} {last}".strip()

                results.append(
                    RawSearchResult(
                        source=self.name,
                        url=f"https://{domain}" if domain else "",
                        title=full_name or email_entry.get("value", ""),
                        snippet=f"{email_entry.get('position', '')} at {org_name}",
                        raw_data={
                            "email": email_entry.get("value", ""),
                            "first_name": first,
                            "last_name": last,
                            "position": email_entry.get("position", ""),
                            "department": email_entry.get("department", ""),
                            "company": org_name,
                            "domain": domain,
                            "confidence": email_entry.get("confidence", 0),
                            "linkedin": email_entry.get("linkedin", ""),
                            "phone_number": email_entry.get("phone_number", ""),
                        },
                    )
                )

            print(f"[Hunter] Found {len(domain_data.get('emails', []))} emails for: {company}")

        except Exception as e:
            print(f"[Hunter] domain-search error: {e}")

    async def _search_by_query(self, search_term: str, results: list[RawSearchResult]):
        """Use Hunter's email-count to check if a domain has public emails."""
        # This is a lighter endpoint — just checks email availability
        params = {
            "domain": search_term,
            "api_key": HUNTER_API_KEY,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.hunter.io/v2/email-count",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        count = data.get("data", {}).get("total", 0)
                        if count > 0:
                            print(f"[Hunter] Found {count} emails for domain: {search_term}")
        except Exception as e:
            print(f"[Hunter] email-count error: {e}")
