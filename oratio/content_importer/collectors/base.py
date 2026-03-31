"""
Abstract base class for all content collectors.

To add a new source site, subclass BaseCollector and implement `fetch()`.
The rest of the pipeline (AI selection, dedup, posting) is automatic.

Optionally implement `fetch_comments()` to import top comments alongside posts.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from models import NormalizedPost, NormalizedComment

logger = logging.getLogger("content_importer.collector")


class BaseCollector(ABC):
    """
    Every collector converts a specific source into a list of NormalizedPost.

    Subclasses only need to implement ``fetch()``.
    Optionally implement ``fetch_comments()`` to support comment importing.
    """

    def __init__(self, source_config: dict):
        self.config = source_config
        self.name: str = source_config.get("name", self.__class__.__name__)

    @abstractmethod
    def fetch(self) -> list[NormalizedPost]:
        """Retrieve posts from the source and return normalized list."""
        ...

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top comments for a specific post, sorted by score descending.

        Override in subclasses that support comment extraction.
        Returns empty list by default (source doesn't support comments).
        """
        return []

    @property
    def supports_comments(self) -> bool:
        """Whether this collector has implemented comment fetching."""
        return type(self).fetch_comments is not BaseCollector.fetch_comments

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
