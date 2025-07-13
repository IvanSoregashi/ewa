import logging
from typing import Any
from pathlib import Path

from ewa.utils.epub.epub_state import EpubState

logger = logging.getLogger(__name__)


def create_epub_data(epub_path: Path, size_threshold: int = 50 * 1024) -> EpubState:
    """Stage 0: Create EpubData object"""
    if not epub_path.exists() or epub_path.suffix.lower() != '.epub':
        raise FileNotFoundError(f"EPUB file not found: {epub_path}")
    
    return EpubState(
        epub_path=epub_path,
        size_threshold=size_threshold,
    )


def extract_epub(data: EpubState) -> EpubState:
    """Stage 1: Extract EPUB to temporary directory"""
    data.extract()    
    return data


def analyze_epub_files(data: EpubState) -> EpubState:
    """Stage 2: Analyze files"""
    data.collect_file_stats()
    return data


def resize_images(data: EpubState, max_workers: int = 50) -> EpubState:
    """Stage 3: Resize images using threading"""
    data.resize_illustrations()
    return data


def update_references(data: EpubState, max_workers: int = 50) -> EpubState:
    """Stage 4: Update image references in chapters"""
    data.update_image_references()
    return data


def package_epub(data: EpubState) -> EpubState:
    """Stage 5: Package the modified EPUB"""
    data.remove_unused_images()
    data.compress_dir_into_epub()
    return data


def create_report(data: EpubState) -> dict[str, Any]:
    """Stage 6: Generate final processing report"""
    errors = [
        result.error
        for result in data.generate_image_processors
        if result.error
    ]

    if errors:
        return {
            "success": False,
            "errors": errors,
            "epub_path": str(data.epub_path)
        }
    
    static_analytics = generate_static_analytics(data)
    #resizing_analytics = generate_resizing_analytics(data)
    
    return {
        "success": True,
        "epub_path": str(data.epub_path),
        "static_analytics": [report.__dict__ for report in static_analytics],
        #"resizing_analytics": [report.__dict__ for report in resizing_analytics]
    }


def cleanup_stage(data: EpubState) -> None:
    if data and data.temp_dir and data.temp_dir.exists():
        import shutil
        try:
            shutil.rmtree(data.temp_dir)
            logger.info(f"Cleaned up temporary directory: {data.temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {data.temp_dir}: {e}")


def process_epub_pipeline(epub_path: Path, size_threshold: int = 50 * 1024) -> dict[str, Any]:
    """Main processing pipeline function"""
    data = None
    try:
        data = create_epub_data(epub_path, size_threshold)
        data = extract_epub(data)
        data = analyze_epub_files(data)
        data = resize_images(data)
        data = update_references(data)
        data = package_epub(data)
        return create_report(data)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return {
            "success": False,
            "errors": [str(e)],
            "epub_path": str(epub_path)
        }
    finally:
        cleanup_stage(data)


def analyze_epub_pipeline(epub_path: Path, size_threshold: int = 50 * 1024) -> dict[str, Any]:
    """Analytics-only pipeline function"""
    data = None
    try:
        data = create_epub_data(epub_path, size_threshold)
        data = extract_epub(data)
        data = analyze_epub_files(data)
        data = resize_images(data)
        return create_report(data)
    except Exception as e:
        logger.error(f"Analytics pipeline failed: {e}")
        return {
            "success": False,
            "errors": [str(e)],
            "epub_path": str(epub_path)
        }
    finally:
        cleanup_stage(data)

