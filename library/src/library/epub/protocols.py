from dataclasses import dataclass
from typing import Protocol

from library.epub.epub import EPUB
from library.epub.resources import Resource


@dataclass(frozen=True)
class VerificationResult:
    """Findings from one verification call, independent of the verifier instance.

    passed says whether the checked condition holds; details explains failures
    or qualifies the check's coverage. A failed check is an expected finding,
    while unexpected execution errors propagate as exceptions. The caller
    decides whether to skip, warn, or repair and owns any book-level analytics.
    Inspect .passed explicitly; this object is not a boolean.
    """

    passed: bool
    details: str = ""


class EpubVerification(Protocol):
    """Common interface for chaining configured checks over an EPUB.

    Implementations return fresh findings and retain no per-book result state.
    Checks inspect the book without editing it; lazy reads/parsing may populate
    caches. They do not collect EpubInfo or decide the recipe's skip policy.
    """

    def verify(self, epub: EPUB) -> VerificationResult: ...


class ResourceVerification(Protocol):
    """The same verification contract applied to a single resource."""

    def verify(self, resource: Resource) -> VerificationResult: ...
