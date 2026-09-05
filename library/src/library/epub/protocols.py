from typing import Protocol

from library.analytics import OperationResult
from library.epub.epub import EPUB
from library.epub.resources import Resource


class EpubVerification(Protocol):
    def verify(self, epub: EPUB) -> bool: ...


class ResourceVerification(Protocol):
    def verify(self, resource: Resource) -> bool: ...


class EpubOperation(Protocol):
    def perform(self, epub: EPUB) -> OperationResult: ...


class ResourceOperation(Protocol):
    def perform(self, resource: Resource) -> OperationResult: ...
