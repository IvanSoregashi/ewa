import json
import logging
import time
from pathlib import Path

from epub.config import settings
from epub.processing_run import ProcessingRun
from epub.image_analytics import ImageOptimizationRecord
from library.asserts import require
from library.epub.epub import EPUB, EpubInfo
from epub.errors import EpubSkipReason, EpubErrorReason
from library.epub.media_type import EpubRole, MediaType
from epub import recipe_image, recipe_htmls
from library.epub import html_editing
from epub import recipe_analytics, recipe_css, recipe_package
from epub.verification import OPFPath, SerenePanda

logger = logging.getLogger(__name__)
sp_dictionary_path: Path = settings.serene_panda_dir / "translator.json"
sp_dictionary = str.maketrans(json.loads(sp_dictionary_path.read_text(encoding="utf-8")))


def fully_process_encrypted_panda(path: str) -> ProcessingRun:
    start = time.time()
    result = _fully_process_encrypted_panda(path)
    print(f"ELAPSED _fully_process_encrypted_panda: {time.time() - start:.2f} s")
    start = time.time()
    recipe_analytics.record_analytics([result], settings.database_url)
    print(f"ELAPSED record_analytics: {time.time() - start:.2f} s")
    return result


def _fully_process_encrypted_panda(path: str) -> ProcessingRun:
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
    run = ProcessingRun(input_path=str(current_path))

    if not current_path.is_relative_to(settings.encrypted_epub_dir):
        logger.warning(f"SKIP {str(current_path)!s} FILE NOT FROM {str(settings.encrypted_epub_dir)!s}")
        # EPUB STAYS IN PLACE
        run.skip = EpubSkipReason.INCORRECT_DIRECTORY
        run.original_epub = EpubInfo.from_path(current_path)
        return run

    relative_path = current_path.relative_to(settings.encrypted_epub_dir)
    destination_path = settings.decrypted_epub_dir / relative_path
    if destination_path.exists():
        logger.warning(f"SKIP {str(current_path)!s} SINCE {str(destination_path)!s} EXISTS")
        # EPUB STAYS IN PLACE
        run.skip = EpubSkipReason.DESTINATION_EXISTS
        run.original_epub = EpubInfo.from_path(current_path)
        return run

    try:
        with EPUB(current_path).keep_open() as epub:
            run.original_epub = epub.info()
            # recipe_package.relocate_package(epub)

            for verification in (OPFPath(), SerenePanda()):
                finding = verification.verify_epub(epub)
                if not finding.passed:
                    logger.warning("SKIP %s: %s", current_path, finding.details)
                    run.skip = verification.skip_reason
                    run.details = finding.details
                    return run

            fonts = [f for f in epub.resources.by_role(EpubRole.FONT) if "serenepanda" in f.filename.lower()]
            font = fonts[0]
            epub.package.remove_resource(font)

            for css_resource in epub.resources.by_role(EpubRole.STYLE):
                recipe_css.de_panda_css_resource(css_resource)

            replacement_dict = {}
            for image_resource in epub.resources.by_role(EpubRole.IMAGE):
                if image_resource.media_type is MediaType.IMAGE_SVG:
                    continue
                result = ImageOptimizationRecord.from_result(
                    run.id, recipe_image.perform_image_optimization(image_resource, resources=epub.resources)
                )
                run.analytics.append(result)
                if result.success and result.new_image and result.new_image.path:
                    old_path = require(result.original_image.path)
                    new_path = result.new_image.path
                    if new_path in replacement_dict.values():
                        new_path += ".jpg"
                    replacement_dict[old_path] = new_path

            htmls = epub.resources.by_role(EpubRole.HTML)
            if replacement_dict:
                string = json.dumps(replacement_dict, indent=4)
                logger.warning(f"{epub} REPLACE:\n{string!s}")

                unmatched = recipe_htmls.replace_links_in_htmls(htmls, replacement_dict=replacement_dict)
                if unmatched:
                    string = json.dumps(unmatched, indent=4)
                    logger.error(f"{epub} LINKS NOT REPLACED:\n{string}")
                    run.skip = EpubSkipReason.UNMATCHED_LINKS
                    run.details = string
                    return run

            for html_resource in htmls:
                html_editing.translate_text(html_resource, sp_dictionary)

            if replacement_dict:
                recipe_package.replace_links(epub, replacement_dict)

            epub.package_into(destination_path, sort_by_role=True)

    except Exception as e:
        logger.exception(f"EPUB FAIL {path}, error: {e}")
        destination_path.unlink(missing_ok=True)  # remove an unfinished epub, if one was written
        run.skip = None  # Source cleanup can fail while returning an eligibility skip.
        run.error = EpubErrorReason.UNKNOWN
        run.details = repr(e)
        return run

    try:
        new_info = EPUB(destination_path).info()
    except Exception as e:
        logger.error(f"EPUB RESULT FAIL {path}, error: {e}")
        destination_path.unlink(missing_ok=True)  # remove the corrupt result
        run.error = EpubErrorReason.INCORRECT_RESULT
        run.details = repr(e)
        return run

    # move original to processed
    try:
        processed_path = settings.processed_epub_dir / relative_path
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        if processed_path.exists():
            logger.warning(f"PROCESSED PATH EXISTS {str(processed_path)!s}, NOT MOVING ORIGINAL")
        else:
            # shutil.move(current_path, processed_path)
            pass
    except Exception as e:
        # housekeeping only: the processed epub is already written and verified,
        # so the result stays a success - the original simply remains in place
        logger.error(f"FAILED TO MOVE ORIGINAL {path} -> {str(processed_path)!s}: {e}")

    destination_path.unlink(missing_ok=True)

    run.success = True
    run.new_epub = new_info
    return run


def image_stats(path: str) -> None:
    current_path = Path(path)
    images: dict[int, list[int]] = {}
    with EPUB(current_path).keep_open() as epub:
        for image_resource in epub.resources.by_role(EpubRole.IMAGE):
            filesize = int(image_resource.info.file_size / 1024)
            percent_comp = int((image_resource.info.compress_size / image_resource.info.file_size) * 100)
            images.setdefault(filesize, []).append(percent_comp)

    for size, list_percent in sorted(images.items()):
        logger.info(f"{size} KB files={len(list_percent)}, avg_percent={sum(list_percent) // len(list_percent)}")
