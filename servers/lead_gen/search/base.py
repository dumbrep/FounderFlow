"""
Abstract base class for all data source adapters.
Every search adapter (Google, Hunter, NewsAPI, etc.) implements this interface.
"""
from abc import ABC, abstractmethod
from servers.lead_gen.models import LeadSearchInput, RawSearchResult


class DataSource(ABC):
    """Base class for data source adapters."""

    name: str = "base"

    @abstractmethod
    async def search(self, query: LeadSearchInput) -> list[RawSearchResult]:
        """
        Search this data source and return raw results.
        Each adapter converts its API response into RawSearchResult objects.
        """
        ...

    def is_available(self) -> bool:
        """Check if this source has its API key configured."""
        return True
