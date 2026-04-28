"""
NewsAPI adapter for recent news and activity discovery.
Finds recent mentions of companies/people in news articles.
"""
import aiohttp
from .base import DataSource
from ..models import LeadSearchInput, RawSearchResult
from ..config import NEWSAPI_KEY, MAX_SEARCH_RESULTS_PER_SOURCE


class NewsAPISource(DataSource):
    name = "newsapi"

    def is_available(self) -> bool:
        return bool(NEWSAPI_KEY)

    async def search(self, query: LeadSearchInput) -> list[RawSearchResult]:
        if not self.is_available():
            return []

        search_query = query.to_search_query()
        results: list[RawSearchResult] = []

        params = {
            "q": search_query,
            "apiKey": NEWSAPI_KEY,
            "pageSize": MAX_SEARCH_RESULTS_PER_SOURCE,
            "sortBy": "relevancy",
            "language": "en",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://newsapi.org/v2/everything",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        print(f"[NewsAPI] returned status {resp.status}")
                        return []
                    data = await resp.json()

            for article in data.get("articles", []):
                results.append(
                    RawSearchResult(
                        source=self.name,
                        url=article.get("url", ""),
                        title=article.get("title", ""),
                        snippet=article.get("description", ""),
                        raw_data={
                            "author": article.get("author", ""),
                            "source_name": article.get("source", {}).get("name", ""),
                            "published_at": article.get("publishedAt", ""),
                            "content": article.get("content", ""),
                        },
                    )
                )

            print(f"[NewsAPI] Found {len(results)} articles for: {search_query}")

        except Exception as e:
            print(f"[NewsAPI] Error: {e}")

        return results
