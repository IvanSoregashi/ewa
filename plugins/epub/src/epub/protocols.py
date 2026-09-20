"""Uniform interfaces for configured plugin checks and operations.

Checks retain configuration and a default skip reason, while each call returns
None or a failure message. Failed checks stop processing as skips. The common library
provides editing/parsing functions and does not depend on these workflow types.
"""

from typing import TYPE_CHECKING, Protocol
from epub.errors import EpubSkipReason
from library.analytics import OperationResult
from library.epub.resources import Resource

if TYPE_CHECKING:
    from epub.processing import ProcessingContext


class EpubVerification(Protocol):
    """A reusable check with a default batch skip reason.

    verify returns None on success or a failure message, without storing per-book state.
    skip_reason is stable configuration used when failure skips the book.
    Checks do not collect book analytics or persist database records.
    Lazy reads/parsing may populate caches; checks do not edit book content.
    """

    skip_reason: EpubSkipReason

    def verify(self, context: ProcessingContext) -> str | None: ...


class ResourceVerification(Protocol):
    """The same verification contract applied to a single resource."""

    def verify(self, resource: Resource) -> str | None: ...


class EpubOperation(Protocol):
    def perform(self, context: ProcessingContext) -> None: ...


class ResourceOperation(Protocol):
    def perform(self, resource: Resource) -> OperationResult: ...
