"""Uniform perform interfaces for the plugin's chainable workflow operations.

General verification contracts remain in library.epub.protocols so checks can
be shared by the library and plugin without a reverse dependency.
"""

from typing import Protocol
from epub.errors import EpubSkipReason
from library.epub.protocols import EpubVerification as LibraryEpubVerification
from library.analytics import OperationResult
from library.epub.epub import EPUB
from library.epub.resources import Resource


class EpubVerification(LibraryEpubVerification, Protocol):
    """A library-compatible check with a default batch skip reason.

    skip_reason is configuration, independent of the current book's findings.
    Recipes can use it when verification fails or choose another response,
    such as warning or repairing. Per-call details remain in VerificationResult.
    """

    skip_reason: EpubSkipReason


class EpubOperation(Protocol):
    def perform(self, epub: EPUB): ...


class ResourceOperation(Protocol):
    def perform(self, resource: Resource) -> OperationResult: ...
