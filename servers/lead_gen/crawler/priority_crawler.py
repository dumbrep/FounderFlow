"""
Priority Queue Crawler with domain hit-rate tracking.
Replaces the RL + MAB approach with a practical heuristic-based crawler
that achieves ~80% of the benefit with ~1% of the complexity.
"""
import asyncio
import heapq
from urllib.parse import urlparse
from collections import defaultdict

from servers.lead_gen.models import LeadSearchInput, PageContent
from servers.lead_gen.crawler.renderer import render_page
from servers.lead_gen.config import MAX_CRAWL_PAGES, MAX_CRAWL_DEPTH, CRAWL_DELAY_SECONDS


class PriorityCrawler:
    """
    A focused crawler that uses a priority queue to visit the most
    promising URLs first, and tracks per-domain hit rates to learn
    which sources yield the best leads over time.
    """

    def __init__(self, query: LeadSearchInput):
        self.query = query
        self.keywords = set(kw.lower() for kw in query.keywords)
        if query.industry:
            self.keywords.add(query.industry.lower())
        if query.persona:
            self.keywords.add(query.persona.lower())
        if query.company:
            self.keywords.add(query.company.lower())

        self.visited: set[str] = set()
        self.domain_hits: dict[str, int] = defaultdict(int)   # leads found per domain
        self.domain_visits: dict[str, int] = defaultdict(int)  # pages visited per domain
        self.pages_crawled = 0

    def _score_url(self, url: str, anchor_text: str = "") -> float:
        """
        Score a URL's priority (lower = higher priority in heapq).
        Considers: keyword matches in URL/anchor, domain hit rate.
        """
        score = 0.0
        url_lower = url.lower()
        anchor_lower = anchor_text.lower()

        # Keyword matches in URL path
        for kw in self.keywords:
            if kw in url_lower:
                score -= 10.0
            if kw in anchor_lower:
                score -= 5.0

        # Domain hit-rate bonus: domains that previously yielded leads get priority
        domain = urlparse(url).netloc
        visits = self.domain_visits.get(domain, 0)
        hits = self.domain_hits.get(domain, 0)
        if visits > 0:
            hit_rate = hits / visits
            score -= hit_rate * 20.0  # High hit-rate domains are prioritized

        # Penalize very deep URLs (usually less useful)
        path_depth = url.count("/") - 2  # subtract protocol slashes
        score += path_depth * 0.5

        # Penalize known low-value patterns
        low_value = ["privacy", "terms", "cookie", "login", "signup", "cart", "checkout"]
        for pattern in low_value:
            if pattern in url_lower:
                score += 50.0  # Strongly deprioritize

        return score

    async def crawl(self, seed_urls: list[str]) -> list[PageContent]:
        """
        Crawl starting from seed URLs, following the priority queue.
        Returns a list of rendered PageContent objects.
        """
        # Initialize the priority queue with scored seed URLs
        # heapq is a min-heap, so lower scores = higher priority
        pq: list[tuple[float, int, str, int]] = []  # (score, counter, url, depth)
        counter = 0

        for url in seed_urls:
            if url and url not in self.visited:
                score = self._score_url(url)
                heapq.heappush(pq, (score, counter, url, 0))
                counter += 1

        results: list[PageContent] = []

        while pq and self.pages_crawled < MAX_CRAWL_PAGES:
            score, _, url, depth = heapq.heappop(pq)

            # Skip if already visited or too deep
            if url in self.visited or depth > MAX_CRAWL_DEPTH:
                continue

            self.visited.add(url)
            domain = urlparse(url).netloc
            self.domain_visits[domain] += 1
            self.pages_crawled += 1

            print(f"[Crawler] ({self.pages_crawled}/{MAX_CRAWL_PAGES}) "
                  f"score={score:.1f} depth={depth} → {url[:80]}")

            # Render the page
            page = await render_page(url)

            if page.text:
                results.append(page)

                # Check if this page seems to have lead-worthy content
                text_lower = page.text.lower()
                keyword_hits = sum(1 for kw in self.keywords if kw in text_lower)
                if keyword_hits > 0:
                    self.domain_hits[domain] += 1

                # Add discovered links to the queue (one level deeper)
                if depth < MAX_CRAWL_DEPTH:
                    for link in page.links:
                        if link not in self.visited:
                            link_score = self._score_url(link)
                            heapq.heappush(pq, (link_score, counter, link, depth + 1))
                            counter += 1

            # Polite delay between requests
            await asyncio.sleep(CRAWL_DELAY_SECONDS)

        print(f"[Crawler] Done. Crawled {self.pages_crawled} pages, "
              f"got {len(results)} with content")

        return results

    def report_lead_found(self, source_url: str):
        """Call this when a lead is extracted from a page to boost that domain."""
        domain = urlparse(source_url).netloc
        self.domain_hits[domain] += 1

    def get_domain_stats(self) -> dict:
        """Return hit-rate statistics per domain."""
        stats = {}
        for domain in set(list(self.domain_visits.keys()) + list(self.domain_hits.keys())):
            visits = self.domain_visits.get(domain, 0)
            hits = self.domain_hits.get(domain, 0)
            stats[domain] = {
                "visits": visits,
                "hits": hits,
                "hit_rate": round(hits / max(visits, 1), 2),
            }
        return stats
