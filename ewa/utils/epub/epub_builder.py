import logging
from pathlib import Path
from typing import Protocol

from ewa.utils.epub.epub_state import EpubState
from ewa.utils.table import print_table

logger = logging.getLogger(__name__)


class EpubContextManager(Protocol):
    """Protocol for EPUB context managers"""
    def __enter__(self) -> 'EpubProcessor': ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...


class EpubProcessor:
    """Builder pattern implementation for EPUB processing"""

    def __init__(self, epub_path: Path):
        self._state = EpubState(epub_path=epub_path)

    def setup(
            self,
            size_threshold: int | None = None,
            max_width: int | None = None,
            max_height: int | None = None,
            quality: int | None = None,
            workers: int | None = None,
            supported_suffixes: tuple[str] | None = None
        ) -> 'EpubProcessor':
        """Setup the EPUB processor"""
        self._state.set_image_resize_settings(
            size_threshold=size_threshold,
            max_width=max_width,
            max_height=max_height,
            quality=quality,
            workers=workers,
            supported_suffixes=supported_suffixes
        )
        return self

    def extract(self) -> 'EpubProcessor':
        """Extract EPUB to temporary directory"""
        if not self._state.epub_path.exists() or self._state.epub_path.suffix.lower() != '.epub':
            raise FileNotFoundError(f"EPUB file not found: {self._state.epub_path}")
        
        self._state.extract()
        return self

    def extracted(self) -> EpubContextManager:
        """Context manager for extracting and cleaning up EPUB"""

        if not self._state.epub_path.exists() or self._state.epub_path.suffix.lower() != '.epub':
            raise FileNotFoundError(f"EPUB file not found: {self._state.epub_path}")
        
        class ExtractedContext:
            def __init__(self, processor: 'EpubProcessor'):
                self.processor: 'EpubProcessor' = processor
            
            def __enter__(self) -> 'EpubProcessor':
                self.processor.extract()
                return self.processor
            
            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                self.processor.teardown()
        
        return ExtractedContext(self)

    def collect_file_stats(self) -> 'EpubProcessor':
        """Collect file statistics"""
        self._state.collect_file_stats()        
        return self

    def resize_images(self) -> 'EpubProcessor':
        """Resize images using threading"""
        if not self._state.file_stats:
            raise ValueError("File statistics not collected")
        self._state.resize_illustrations()
        return self

    def update_image_references(self) -> 'EpubProcessor':
        """Update image references in chapters"""
        if not self._state.image_processors:
            raise ValueError("Image processors were not engaged")
        self._state.update_image_references()
        return self

    def package(self) -> 'EpubProcessor':
        """Package the modified EPUB"""
        if not self._state.chapter_results:
            raise ValueError("Chapter were not updated")
        self._state.remove_unused_images()
        self._state.compress_dir_into_epub()
        return self
    
    def teardown(self) -> 'EpubProcessor':
        """Teardown the EPUB processor"""
        self._state.teardown()
        return self
    
    def print_file_report(self) -> 'EpubProcessor':
        """Generate file report"""
        print_table(self._state.file_report(), title="File Report")
        return self
    
    def print_resize_report(self) -> 'EpubProcessor':
        """Generate resize report"""
        print_table(self._state.resize_report(), title="Resize Report")
        return self
    
    def print_chapter_report(self) -> 'EpubProcessor':
        """Generate chapter report"""
        print_table(self._state.chapter_report(), title="Chapter Report")
        return self
