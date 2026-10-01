import json
import logging
import shutil
import time
from pathlib import Path

from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import EpubRole, FileName

from epub import recipe_analytics
from epub.config import settings
from epub.processing import ProcessingContext
from epub.processing_run import ProcessingRun
from epub.recipe_css import CleanupPandaCSS
from epub.recipe_htmls import RemoveResourceAndManifest, ReplaceLinks, TextTranslator
from epub.recipe_image import OptimizeImages
from epub.recipe_package import PackageEpub
from epub.schema_stats import EpubSchemaStats
from epub.verification import NoUnmatchedLinks, OPFPath, SerenePanda

logger = logging.getLogger(__name__)
sp_dictionary_path: Path = settings.serene_panda_dir / "translator.json"
sp_dictionary: dict[int, str | int | None] | None = None


def get_sp_dictionary() -> dict[int, str | int | None]:
    global sp_dictionary
    if sp_dictionary is None:
        sp_dictionary = str.maketrans(json.loads(sp_dictionary_path.read_text(encoding="utf-8")))
    return sp_dictionary


def should_process_path(path: Path) -> bool:
    if not path.is_relative_to(settings.encrypted_epub_dir):
        logger.warning("SKIP %s FILE NOT FROM %s", path, settings.encrypted_epub_dir)
        return False
    destination = settings.decrypted_epub_dir / path.relative_to(settings.encrypted_epub_dir)
    if destination.exists():
        logger.warning("SKIP %s SINCE %s EXISTS", path, destination)
        return False
    return True


def fully_process_encrypted_panda(path: str, *, dry_run: bool = False) -> ProcessingRun:
    start = time.time()
    result = _fully_process_encrypted_panda(path, dry_run=dry_run)
    print(f"ELAPSED _fully_process_encrypted_panda: {time.time() - start:.2f} s")
    start = time.time()
    recipe_analytics.record_analytics([result], settings.database_url)
    print(f"ELAPSED record_analytics: {time.time() - start:.2f} s")
    return result


def process_encrypted_panda_no_relink(path: str, *, dry_run: bool = False) -> ProcessingRun:
    start = time.time()
    result = _process_encrypted_panda_no_relink(path, dry_run=dry_run)
    print(f"ELAPSED _process_encrypted_panda_no_relink: {time.time() - start:.2f} s")
    start = time.time()
    recipe_analytics.record_analytics([result], settings.database_url)
    print(f"ELAPSED record_analytics: {time.time() - start:.2f} s")
    return result


def _fully_process_encrypted_panda(path: str, *, dry_run: bool = False) -> ProcessingRun:
    current_path = Path(path)
    relative_path = current_path.relative_to(settings.encrypted_epub_dir)
    destination_path = settings.decrypted_epub_dir / relative_path
    processed_path = settings.processed_epub_dir / relative_path

    with ProcessingContext() as context:
        context.open_epub(current_path).verify(OPFPath(), SerenePanda())
        # Keep the existing recipe's first-font removal, including relaxed checks.
        font = context.epub.resources.by_role(EpubRole.FONT)[0]
        context.perform(RemoveResourceAndManifest(exact_path=font.filename, flush=False))
        context.perform(CleanupPandaCSS())
        context.perform(OptimizeImages())
        context.perform(ReplaceLinks()).verify(NoUnmatchedLinks())
        context.perform(TextTranslator(get_sp_dictionary()))
        context.perform(PackageEpub(destination_path))

    run = require(context.result)
    if not run.success:
        if run.error is not None:
            try:
                destination_path.unlink(missing_ok=True)
            except OSError as error:
                run.details += f"\nRemoving failed output: {error!r}"
            logger.error("EPUB FAIL %s: %s", path, run.details)
        else:
            logger.warning("SKIP %s: %s", path, run.details)
        return run

    move_the_files(current_path, processed_path, destination_path, dry_run=dry_run)
    return run


def _process_encrypted_panda_no_relink(path: str, *, dry_run: bool = False) -> ProcessingRun:
    current_path = Path(path)
    relative_path = current_path.relative_to(settings.encrypted_epub_dir)
    destination_path = settings.decrypted_epub_dir / relative_path
    processed_path = settings.processed_epub_dir / relative_path

    with ProcessingContext() as context:
        context.open_epub(current_path).verify(SerenePanda())
        context.perform(RemoveResourceAndManifest(path=FileName.SP_FONT_LOWER_ENDSWITH, flush=False))
        context.perform(CleanupPandaCSS())
        context.perform(OptimizeImages())
        context.perform(ReplaceLinks())
        save_unmatched_links(context, relative_path)
        context.perform(TextTranslator(get_sp_dictionary()))
        context.perform(PackageEpub(destination_path))

    run = require(context.result)
    if not run.success:
        if run.error is not None:
            try:
                destination_path.unlink(missing_ok=True)
            except OSError as error:
                run.details += f"\nRemoving failed output: {error!r}"
            logger.error("EPUB FAIL %s: %s", path, run.details)
        else:
            logger.warning("SKIP %s: %s", path, run.details)
        return run

    move_the_files(current_path, processed_path, destination_path, dry_run=dry_run)
    return run


def save_unmatched_links(context: ProcessingContext, relative_path: Path) -> None:
    report_path = settings.epub_settings_dir / "unmatched_links" / (relative_path.name + ".json")
    try:
        if context.unmatched_links or context.unmatched_manifest_links:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            json_dict = {
                "unmatched_links": context.unmatched_links,
                "unmatched_manifest_links": context.unmatched_manifest_links,
            }
            report_path.write_text(json.dumps(json_dict, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.warning("Unmatched links saved to %s", report_path)
        else:
            report_path.unlink(missing_ok=True)
    except OSError as error:
        logger.warning("Could not update unmatched-link report %s: %s", report_path, error)


def move_the_files(current_path: Path, processed_path: Path, destination_path: Path, *, dry_run: bool) -> None:
    """Dry runs still process, validate, and record analytics; discard only their output."""
    if dry_run:
        logger.info("DRY RUN: leaving original %s in place; removing output %s", current_path, destination_path)
        try:
            destination_path.unlink(missing_ok=True)
        except OSError as error:
            logger.error("FAILED TO REMOVE DRY-RUN OUTPUT %s: %s", destination_path, error)
        return

    try:
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        if processed_path.exists():
            logger.warning(f"PROCESSED PATH EXISTS {str(processed_path)!s}, NOT MOVING ORIGINAL")
        else:
            shutil.move(current_path, processed_path)
    except Exception as e:
        # housekeeping only: the processed epub is already written and verified,
        # so the result stays a success - the original simply remains in place
        logger.error(f"FAILED TO MOVE ORIGINAL {current_path} -> {str(processed_path)!s}: {e}")


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


def trying_to_get_stats(path: str | Path) -> EpubSchemaStats:
    current_path = Path(path).expanduser().resolve()
    ess = EpubSchemaStats(filepath=str(current_path))

    with EPUB(current_path).keep_open() as epub:
        ess.has_titlepage = epub.resources.by_path("titlepage.xhtml") is not None
        ess.has_stylesheet = epub.resources.by_path("stylesheet.css") is not None
        ess.has_page_styles = epub.resources.by_path("page_styles.css") is not None
        ess.has_content = epub.resources.by_path("content.opf") is not None
        ess.has_toc = epub.resources.by_path("toc.ncx") is not None
        ess.fonts = len(epub.resources.by_role(EpubRole.FONT))

        package = epub.package.document
        metadata = package.metadata

        ess.len_creators = len(metadata.creators)
        ess.len_contributors = len(metadata.contributors)
        ess.len_identifiers = len(metadata.identifiers)

        guide = package.guide
        if guide is not None and guide.references:
            first_reference = guide.references[0]
            # <reference type="cover" href="titlepage.xhtml" title="Cover"/>
            ess.guide_type = first_reference.type
            ess.guide_href = first_reference.href
            ess.guide_title = first_reference.title

        if metadata.creators:
            first_creator = metadata.creators[0]
            ess.creator_file = first_creator.file_as or first_creator.file_as_ns
            ess.creator_role = first_creator.role or first_creator.role_ns
            ess.creator_text = first_creator.text

        if metadata.contributors:
            first_contributor = metadata.contributors[0]
            ess.contributor_role = first_contributor.role or first_contributor.role_ns
            ess.contributor_text = first_contributor.text

        if metadata.identifiers:
            first_identifier = metadata.identifiers[0]
            ess.identifier_id = first_identifier.id
            ess.identifier_scheme = first_identifier.scheme or first_identifier.scheme_ns

        ess.has_calibre_ts = any(meta.name == "calibre:timestamp" for meta in metadata.metas)
        ess.has_cover_cover = any(meta.name == "cover" and meta.content == "cover" for meta in metadata.metas)

    return ess
