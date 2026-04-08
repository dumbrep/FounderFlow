"""
Google Search adapter using SerpAPI.
This is the primary discovery source — finds company pages, LinkedIn profiles,
news articles, and directories via Google search.
"""
import aiohttp
from servers.lead_gen.search.base import DataSource
from servers.lead_gen.models import LeadSearchInput, RawSearchResult
from servers.lead_gen.config import SERPAPI_KEY, MAX_SEARCH_RESULTS_PER_SOURCE


class GoogleSearchSource(DataSource):
    name = "google"

    def is_available(self) -> bool:
        return bool(SERPAPI_KEY)

    async def search(self, query: LeadSearchInput) -> list[RawSearchResult]:
        if not self.is_available():
            return []

        search_query = query.to_search_query()
        results: list[RawSearchResult] = []

        params = {
            "q": search_query,
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": MAX_SEARCH_RESULTS_PER_SOURCE,
            "gl": "us",
            "hl": "en",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://serpapi.com/search.json",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        print(f"[GoogleSearch] SerpAPI returned status {resp.status}")
                        return []
                    data = await resp.json()

            # Parse organic results
            for item in data.get("organic_results", []):
                results.append(
                    RawSearchResult(
                        source=self.name,
                        url=item.get("link", ""),
                        title=item.get("title", ""),
                        snippet=item.get("snippet", ""),
                        raw_data={
                            "position": item.get("position"),
                            "displayed_link": item.get("displayed_link", ""),
                            "date": item.get("date", ""),
                        },
                    )
                )

            # Also grab knowledge graph if present (rich company info)
            kg = data.get("knowledge_graph", {})
            if kg:
                results.append(
                    RawSearchResult(
                        source=self.name,
                        url=kg.get("website", kg.get("link", "")),
                        title=kg.get("title", ""),
                        snippet=kg.get("description", ""),
                        raw_data={
                            "type": "knowledge_graph",
                            "entity_type": kg.get("type", ""),
                            "attributes": kg.get("attributes", {}),
                        },
                    )
                )

            print(f"[GoogleSearch] Found {len(results)} results for: {search_query}")

        except Exception as e:
            print(f"[GoogleSearch] Error: {e}")

        return results
