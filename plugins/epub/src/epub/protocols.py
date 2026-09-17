"""Uniform perform interfaces for the plugin's chainable workflow operations.

General verification contracts remain in library.epub.protocols so checks can
be shared by the library and plugin without a reverse dependency.
"""

from typing import Protocol
from library.analytics import OperationResult
from library.epub.epub import EPUB
from library.epub.resources import Resource


class EpubOperation(Protocol):
    def perform(self, epub: EPUB): ...


class ResourceOperation(Protocol):
    def perform(self, resource: Resource) -> OperationResult: ...
