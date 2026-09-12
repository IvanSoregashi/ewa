from typing import Protocol

from epub.results import EpubOperationResult
from library.analytics import OperationResult
from library.epub.epub import EPUB, EpubInfo
from library.epub.resources import Resource


class EpubVerification(Protocol):
    warning: str
    skip: int
    additional_info: str
    epub_info: EpubInfo

    def verify(self, epub: EPUB) -> bool: ...

    def skipped(self) -> EpubOperationResult:
        return EpubOperationResult(skip=self.skip, original_epub=self.epub_info)


class ResourceVerification(Protocol):
    def verify(self, resource: Resource) -> bool: ...


class EpubOperation(Protocol):
    def perform(self, epub: EPUB): ...


class ResourceOperation(Protocol):
    def perform(self, resource: Resource) -> OperationResult: ...
