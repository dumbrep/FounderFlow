"""
Proxycurl adapter for LinkedIn profile data.
Legal third-party API to get LinkedIn-style data without scraping.
"""
import aiohttp
from .base import DataSource
from ..models import LeadSearchInput, RawSearchResult
from ..config import PROXYCURL_API_KEY, MAX_SEARCH_RESULTS_PER_SOURCE


class ProxycurlSource(DataSource):
    name = "proxycurl"

    def is_available(self) -> bool:
        return bool(PROXYCURL_API_KEY)

    async def search(self, query: LeadSearchInput) -> list[RawSearchResult]:
        if not self.is_available():
            return []

        results: list[RawSearchResult] = []

        # Use the Person Search API to find people matching criteria
        await self._search_people(query, results)

        # If a company is specified, also search for company details
        if query.company:
            await self._search_company(query.company, results)

        return results[:MAX_SEARCH_RESULTS_PER_SOURCE]

    async def _search_people(self, query: LeadSearchInput, results: list[RawSearchResult]):
        """Search for people matching the target profile."""
        params = {}
        if query.company:
            params["current_company_name"] = query.company
        if query.persona:
            params["current_role_title"] = query.persona
        if query.industry:
            params["industry"] = query.industry
        if query.location:
            params["country"] = query.location

        if not params:
            # Need at least one filter
            if query.keywords:
                params["current_role_title"] = " ".join(query.keywords)
            else:
                return

        params["page_size"] = min(MAX_SEARCH_RESULTS_PER_SOURCE, 10)
        params["enrich_profiles"] = "enrich"

        headers = {"Authorization": f"Bearer {PROXYCURL_API_KEY}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://nubela.co/proxycurl/api/search/person/",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        print(f"[Proxycurl] person search returned {resp.status}")
                        return
                    data = await resp.json()

            for person in data.get("results", []):
                profile = person.get("profile", {})
                full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()

                experiences = profile.get("experiences", [])
                current_role = ""
                current_company = ""
                if experiences:
                    current_role = experiences[0].get("title", "")
                    current_company = experiences[0].get("company", "")

                results.append(
                    RawSearchResult(
                        source=self.name,
                        url=profile.get("public_identifier", ""),
                        title=full_name,
                        snippet=f"{current_role} at {current_company}",
                        raw_data={
                            "linkedin_url": person.get("linkedin_profile_url", ""),
                            "first_name": profile.get("first_name", ""),
                            "last_name": profile.get("last_name", ""),
                            "headline": profile.get("headline", ""),
                            "summary": profile.get("summary", ""),
                            "city": profile.get("city", ""),
                            "country": profile.get("country_full_name", ""),
                            "current_role": current_role,
                            "current_company": current_company,
                            "connections": profile.get("connections", 0),
                            "experiences": experiences[:3],  # Keep last 3 roles
                        },
                    )
                )

            print(f"[Proxycurl] Found {len(results)} people")

        except Exception as e:
            print(f"[Proxycurl] person search error: {e}")

    async def _search_company(self, company_name: str, results: list[RawSearchResult]):
        """Get company details from Proxycurl."""
        params = {
            "company_name": company_name,
            "enrich_profiles": "skip",
        }
        headers = {"Authorization": f"Bearer {PROXYCURL_API_KEY}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://nubela.co/proxycurl/api/linkedin/company/resolve",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json()

            if data.get("url"):
                results.append(
                    RawSearchResult(
                        source=self.name,
                        url=data.get("url", ""),
                        title=company_name,
                        snippet=f"LinkedIn company page for {company_name}",
                        raw_data={
                            "type": "company_profile",
                            "linkedin_url": data.get("url", ""),
                        },
                    )
                )

        except Exception as e:
            print(f"[Proxycurl] company search error: {e}")
