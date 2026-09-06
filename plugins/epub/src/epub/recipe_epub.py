import json
import logging
from pathlib import Path

from epub.config import settings
from epub.results import EpubOptimizationResult
from library.epub.epub import EPUB, EpubInfo
from library.epub.errors import EpubSkipReason, EpubErrorReason
from library.epub.media_type import EpubRole, FileName
from library.epub import recipe_image, recipe_html
from epub import recipe_analytics, recipe_css, recipe_package

logger = logging.getLogger(__name__)
sp_dictionary_path: Path = settings.serene_panda_dir / "translator.json"
sp_dictionary = str.maketrans(json.loads(sp_dictionary_path.read_text(encoding="utf-8")))


def fully_process_encrypted_panda(path: str) -> EpubOptimizationResult:
    result = _fully_process_encrypted_panda(path)
    recipe_analytics.record_analytics([result], settings.database_url)
    return result


def _fully_process_encrypted_panda(path: str) -> EpubOptimizationResult:
    """

    1. Check EPUB eligibility
    2. relocate opf to root -> content.opf
    3. font check, remove sp font resource, remove from manifest
    4. cleanup css
    5. images - optimization (all images)
    6. put stats in db
    7. form replacement dict
    8. htmls - replace links, translate
    9. replace links - in opf
    10. save opf
    11. save epub
    12. verify formed epub
    13. move original
    """
    current_path = Path(path)
    if not current_path.is_relative_to(settings.encrypted_epub_dir):
        logger.warning(f"SKIP {str(current_path)!s} FILE NOT FROM {str(settings.encrypted_epub_dir)!s}")
        # EPUB STAYS IN PLACE
        return EpubOptimizationResult(
            skip=EpubSkipReason.INCORRECT_DIRECTORY,
            original_epub=EpubInfo.failed(current_path),
        )

    relative_path = current_path.relative_to(settings.encrypted_epub_dir)
    destination_path = settings.decrypted_epub_dir / relative_path
    if destination_path.exists():
        logger.warning(f"SKIP {str(current_path)!s} SINCE {str(destination_path)!s} EXISTS")
        # EPUB STAYS IN PLACE
        return EpubOptimizationResult(
            skip=EpubSkipReason.DESTINATION_EXISTS,
            original_epub=EpubInfo.failed(current_path),
        )

    try:
        with EPUB(current_path).keep_open() as epub:
            original_info = epub.info()
            # recipe_package.relocate_package(epub)
            for f in epub.resources.by_role(EpubRole.OPF):
                if f.filename != FileName.DEFAULT_OPF:
                    # EPUB STAYS IN PLACE
                    return EpubOptimizationResult(
                        skip=EpubSkipReason.NON_DEFAULT_OPF,
                        original_epub=original_info,
                    )

            fonts = [f for f in epub.resources.by_role(EpubRole.FONT) if "serenepanda" in f.filename.lower()]
            if len(fonts) != 1 or fonts[0].filename != FileName.SP_FONT:
                # EPUB STAYS IN PLACE
                return EpubOptimizationResult(
                    skip=EpubSkipReason.NOT_IMPLEMENTED,
                    original_epub=original_info,
                )
            font = fonts[0]
            epub.resources.remove(font)
            epub.core.package.manifest.remove_item(path=font.filename)

            for css_resource in epub.resources.by_role(EpubRole.STYLE):
                recipe_css.de_panda_css_resource(css_resource)

            image_optimization_results = [
                recipe_image.perform_image_optimization(image_resource)
                for image_resource in epub.resources.by_role(EpubRole.IMAGE)
            ]

            replacement_dict = {}
            for result in image_optimization_results:
                if result.success and result.new_image and result.new_image.path:
                    old_path = result.original_image.path
                    new_path = result.new_image.path
                    if new_path in replacement_dict.values():
                        new_path += ".jpg"
                    replacement_dict[old_path] = new_path

            for html_resource in epub.resources.by_role(EpubRole.HTML):
                if replacement_dict:
                    recipe_html.replace_links(html_resource, replacement_dict)
                recipe_html.translate_text(html_resource, sp_dictionary)

            if replacement_dict:
                recipe_package.replace_links(epub, replacement_dict)
            epub.core.package_resource.content = epub.core.package.to_xml_bytes()

            epub.package_into(destination_path, sort_by_role=True)

    except Exception as e:
        logger.exception(f"EPUB FAIL {path}, error: {e}")
        # MOVE TO QUARANTINE OR STAY IN PLACE?
        return EpubOptimizationResult(
            error=EpubErrorReason.UNKNOWN,
            original_epub=EpubInfo.failed(current_path),
        )

    try:
        new_info = EPUB(destination_path).info()
    except Exception as e:
        logger.error(f"EPUB RESULT FAIL {path}, error: {e}")
        # MOVE DESTINATION TO QUARANTINE
        # EPUB STAYS IN PLACE
        return EpubOptimizationResult(
            error=EpubErrorReason.INCORRECT_RESULT,
            original_epub=EpubInfo.failed(current_path),
        )

    # move original to processed
    processed_path = settings.processed_epub_dir / relative_path
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    if processed_path.exists():
        logger.warning(f"PROCESSED PATH EXISTS {str(processed_path)!s}, NOT MOVING ORIGINAL")
    else:
        # shutil.move(current_path, processed_path)
        pass

    return EpubOptimizationResult(
        success=True,
        original_epub=original_info,
        new_epub=new_info,
        image_results=image_optimization_results,
    )


def image_stats(path: str) -> None:
    current_path = Path(path)
    counter = 0
    images: dict[int, list[int]] = {}
    with EPUB(current_path).keep_open() as epub:
        for image_resource in epub.resources.by_role(EpubRole.IMAGE):
            filesize = int(image_resource.info.file_size / 1024)
            percent_comp = int((image_resource.info.compress_size / image_resource.info.file_size) * 100)
            image_info = recipe_image.get_image_info(image_resource)
            images.setdefault(filesize, []).append(percent_comp)

    for size, list_percent in sorted(images.items()):
        logger.info(f"{size} KB files={len(list_percent)}, avg_percent={sum(list_percent) // len(list_percent)}")
