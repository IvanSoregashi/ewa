import json
import shutil
from dataclasses import dataclass
from pathlib import Path
import logging


from epub.config import settings
from library.analytics import OperationResult
from library.epub.epub import EPUB, EpubInfo
from library.epub.errors import EpubSkipReason, EpubErrorReason
from library.epub.media_type import EpubRole, FileName
from library.epub import recipe_image, recipe_html
from epub import recipe_analytics, recipe_css, recipe_package

logger = logging.getLogger(__name__)
sp_dictionary_path: Path = settings.serene_panda_dir / "translator.json"
sp_dictionary = str.maketrans(json.loads(sp_dictionary_path.read_text(encoding="utf-8")))


@dataclass(kw_only=True)
class EpubOptimizationResult(OperationResult):
    original_epub: EpubInfo
    new_epub: EpubInfo | None = None


def fully_process_encrypted_panda(path: str) -> EpubOptimizationResult:
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
            # 0. standardize the archive layout: opf at the root
            recipe_package.relocate_package(epub)

            # 1. remove font
            fonts = [f for f in epub.resources.by_role(EpubRole.FONT) if "serenepanda" in f.filename.lower()]
            if len(fonts) != 1 or fonts[0].filename != FileName.SP_FONT:
                # EPUB STAYS IN PLACE
                return EpubOptimizationResult(
                    skip=EpubSkipReason.NOT_IMPLEMENTED,
                    original_epub=EpubInfo.failed(current_path),
                )
            font = fonts[0]
            epub.resources.remove(font)
            epub.core.package.manifest.remove_item(path=font.filename)

            # 2. cleanup css
            for css_resource in epub.resources.by_role(EpubRole.STYLE):
                recipe_css.de_panda_css_resource(css_resource)

            # 3. all image resources - through optimization
            image_optimization_results = [
                recipe_image.perform_image_optimization(image_resource)
                for image_resource in epub.resources.by_role(EpubRole.IMAGE)
            ]

            # 3.1. received statistics - save conversion info to SQL
            recipe_analytics.record_image_statistics(current_path, image_optimization_results, settings.database_url)

            # 3.2. received statistics - form a path replacement dictionary
            # (keys/values are archive paths; opf is at the root, so manifest hrefs match)
            replacement_dict = {}
            for result in image_optimization_results:
                if result.success and result.new_image and result.new_image.path:
                    old_path = result.original_image.path
                    new_path = result.new_image.path
                    if new_path in replacement_dict.values():
                        new_path += ".jpg"
                    replacement_dict[old_path] = new_path

            # 4. for the html resources:
            for html_resource in epub.resources.by_role(EpubRole.HTML):
                # - if path replacement dictionary - make replacements
                if replacement_dict:
                    recipe_html.replace_links(html_resource, replacement_dict)
                # - translate
                recipe_html.translate_text(html_resource, sp_dictionary)

            # 5. package: apply renames to the manifest, drop the font item from
            #    the package document itself, and sync the parsed package into its resource
            if replacement_dict:
                recipe_package.replace_links(epub, replacement_dict)
            epub.core.package_resource.content = epub.core.package.to_xml_bytes()

            # 6. Save the updated epub: package_into assembles the archive in a
            #    buffer internally and only touches the destination on success.
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
        shutil.move(current_path, processed_path)

    return EpubOptimizationResult(success=True, original_epub=original_info, new_epub=new_info)
