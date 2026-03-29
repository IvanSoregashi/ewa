from abc import ABC, abstractmethod
from pathlib import Path

from library.chapter.model import Chapter


class ChapterStorage(ABC):
    """Abstract base class for Chapter storage backends."""

    @abstractmethod
    def save(self, chapter: Chapter, path: str | Path) -> None:
        """Save a Chapter to the specified path."""
        pass

    @abstractmethod
    def load(self, path: str | Path) -> Chapter:
        """Load a Chapter from the specified path."""
        pass
