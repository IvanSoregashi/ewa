"""Uniform interfaces for configured plugin checks and operations.

Checks retain configuration and a default skip reason, while each call returns
fresh findings. Failed eligibility checks stop processing as skips. The common library
provides editing/parsing functions and does not depend on these workflow types.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from epub.errors import EpubSkipReason
from library.analytics import OperationResult
from library.epub.resources import Resource

if TYPE_CHECKING:
    from epub.processing import ProcessingContext


@dataclass(frozen=True)
class VerificationResult:
    """Findings from one verification call, independent of the verifier instance.

    passed says whether the checked condition holds; details explains failures
    or qualifies the check's coverage. A failed check is an expected finding,
    while unexpected execution errors propagate as exceptions. The processing
    context consumes the result and stops on failure with a skip.
    Inspect .passed explicitly; this object is not a boolean.
    """

    passed: bool
    details: str = ""


class EpubVerification(Protocol):
    """A reusable check with a default batch skip reason.

    verify inspects a book and returns findings without storing per-book state.
    skip_reason is stable configuration used when failure skips the book.
    Checks do not collect book analytics or persist database records.
    Lazy reads/parsing may populate caches; checks do not edit book content.
    """

    skip_reason: EpubSkipReason

    def verify(self, context: ProcessingContext) -> VerificationResult: ...


class ResourceVerification(Protocol):
    """The same verification contract applied to a single resource."""

    def verify(self, resource: Resource) -> VerificationResult: ...


class EpubOperation(Protocol):
    def perform(self, context: ProcessingContext) -> None: ...


class ResourceOperation(Protocol):
    def perform(self, resource: Resource) -> OperationResult: ...
