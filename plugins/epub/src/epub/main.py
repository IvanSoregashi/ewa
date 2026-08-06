import logging
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import chain

import typer
from pathlib import Path

from sqlalchemy.exc import PendingRollbackError
from sqlmodel import col

from epub.serene_panda import orchestration
from ewa.ui import print_success, print_error
from ewa.cli.print_table import print_table_from_models, print_table_from_dicts
from ewa.cli.progress import DisplayProgress
from ewa.main import settings
from epub.tables import EpubBookTable, EpubContentsTable, EpubOpfHash, EpubHashTable
from library.epub.epub_core import EpubSpecification
from library.epub.utils_css import parse_css_urls, replace_css_url
from library.epub.utils_href import posix_relative_href
from library.epub.xml_models.package_document import PackageDocument
from library.utils import sanitize_filename
from library.epub.epub import EPUB
from epub.config import settings


app = typer.Typer(help="Epub Plugin")
logger = logging.getLogger("EPUB")


# Entry point for the plugin loader
def plugin():
    return app


@app.callback()
def setup():
    """Initialize the database on first run."""
    print_success(f"setup callback called, settings: {settings.model_dump_json(indent=4)}")


@app.command()
def decrypt(epub_path: Path = typer.Argument(None, exists=True)):
    changes_dir = settings.current_dir / "changes"
    changes_dir.mkdir(parents=True, exist_ok=True)

    new_name = epub_path.with_stem(epub_path.stem.replace("(Encoded)", "").strip()).name
    destination = changes_dir / new_name

    with EPUB(epub_path).stream_to(destination) as epub:
        epub.require_specification(EpubSpecification.SERENE_PANDA_ENCRYPTED)

        assert len(epub.resources.fonts) == 1, "SEVERAL FONTS FOUND"
        font_resource = epub.resources.fonts[0]
        font_resource.write_to_filesystem(settings.serene_panda_fonts_dir / font_resource.hash_prefixed_name)

        epub.core.remove_resource(font_resource)

        for style_resource in epub.resources.styles:
            relative_path = posix_relative_href(
                anchor=style_resource.info.filename, absolute_href=font_resource.info.filename
            )
            if relative_path in parse_css_urls(style_resource.content):
                style_resource.content = replace_css_url(
                    style_resource.content, relative_path, font_resource.hash_prefixed_name
                )
                style_resource.is_modified = True

        dictionary = orchestration.translation_dictionary()
        for content_resource in epub.resources.markup_content:
            if content_resource.spine_item_ref is None:
                logger.warning(f"content_resource {content_resource.info.filename} is not in the spine")
            content_resource.content = content_resource.content.decode("utf-8").translate(dictionary).encode("utf-8")
            # content_resource.content = pretty_print_bs4_bytes(content_resource.content)
            content_resource.is_modified = True

        epub.core.remove_garbage()


@app.command("showres")
def check_epub_resources(epub: Path = typer.Argument(None, exists=True)):
    from library.epub.epub import EPUB

    start_time = time.time()
    e = EPUB(epub)
    with e.source.open():
        e.resources.interlink_resources()
        core, common, content, unknown = e.core.resources.statistics()
        print_table_from_dicts(title="CORE", dicts=core)
        print_table_from_dicts(title="COMMON", dicts=common)
        print_table_from_dicts(title="CONTENT", dicts=content)
        if unknown:
            print_table_from_dicts(title="UNKNOWN", dicts=unknown)
    end_time = time.time()
    print_success(f"success in {end_time - start_time:.5f} seconds")


@app.command()
def count(
    files: bool = typer.Option(False, "-f", "--files"),
    rows: bool = typer.Option(False, "-r", "--rows"),
):
    if files:
        print_success(f"Counting epub files in {settings.current_dir}...")
        print_success(f"{len(tuple(Path(settings.current_dir).rglob('*.epub')))} epub files found")
    if rows:
        with EpubContentsTable(settings.database_url) as table:
            print_success(f"Counting epub file records in {table.model.__tablename__} SQL table...")
            print_success(f"{table.count_rows()} total rows of files found")
        with EpubBookTable(settings.database_url) as table:
            print_success(f"Counting epub file records in {table.model.__tablename__} SQL table...")
            print_success(f"{table.count_rows()} total rows of epubs found")


@app.command()
def drop(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
):
    if files:
        with EpubBookTable(settings.database_url) as table:
            table.drop()
            print_success(f"dropped table {table.model.__tablename__}")
    if contents:
        with EpubContentsTable(settings.database_url) as table:
            table.drop()
            print_success(f"dropped table {table.model.__tablename__}")


@app.command("list")
def list_scanned_files(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
    largest: str = typer.Option("", "-l", "--largest"),
):
    """Lists all scanned books."""
    if files:
        with EpubBookTable(settings.database_url) as table:
            raw_rows = table.get_many(limit=10)
            if not raw_rows:
                print_error(f"Table {table.model.__tablename__} is empty")
                return
            print_table_from_models("My Library", raw_rows)
    if contents:
        with EpubContentsTable(settings.database_url) as table:
            raw_rows = table.get_many(limit=10)
            if not raw_rows:
                print_error(f"Table {table.model.__tablename__} is empty")
                return
            print_table_from_models("My Library", raw_rows)


@app.command("move-sp")
def move_serene_panda_encrypted_separately():
    epub_dir = settings.epub_dir
    destination_dir = settings.epub_uwumtl_dir
    start_time = time.time()
    processed = 0
    moved = 0

    for file in epub_dir.rglob("*.epub"):
        try:
            epub = EPUB(file)
            opf = epub.resources.by_path("content.opf")
            package_document = PackageDocument.from_xml_bytes(opf.content)
            # package_document = epub.core.package_document
            author = package_document.metadata.creators[0].text
            if author != "Uwumtl":
                logger.info(f"SKIPPING [{author}]: {str(file)!r}")
                processed += 1
                continue
        except ValueError as e:
            logger.error(f"ValueError [NON-Uwumtl]: {str(file)!r}\n{e!r}")
            continue
        except Exception as e:
            logger.error(f"Exception [NON-Uwumtl]: {str(file)!r}\n{e!r}")
            continue
        processed += 1

        relative_path = file.relative_to(epub_dir)
        new_path = destination_dir / relative_path
        new_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"MOVING [Uwumtl]: {str(file)!r} -> {str(new_path)!r}")
        shutil.move(str(file), str(new_path))
        moved += 1
        logger.info(f"PROCESSED: {processed}, MOVED: {moved}, ELAPSED: {time.time() - start_time}")


@app.command("scan-hash")
def scan_for_hashes():
    epub_dir = settings.epub_dir
    uwu_dir = settings.epub_uwumtl_dir
    encrypted_dir = settings.encrypted_epub_dir
    start_time = time.time()

    with EpubHashTable(settings.database_url) as table:
        table.drop()
        table.create()
        for file in chain(epub_dir.rglob("*.epub"), uwu_dir.rglob("*.epub"), encrypted_dir.rglob("*.epub")):
            try:
                epub = EPUB(file)
                package_document = epub.core.package_document

                ncx_path = None
                ncx_hash = None
                ncx_resource = epub.core.ncx_resource
                if ncx_resource is not None:
                    ncx_path = ncx_resource.info.filename
                    ncx_hash = ncx_resource.hex_hash

                epub_hash_item = EpubOpfHash(
                    filepath=str(file),
                    title=package_document.metadata.title,
                    author=package_document.metadata.aut_or_all_creators,
                    identifier=package_document.metadata.uuid_id_or_all_identifiers,
                    opf_path=epub.core.package_resource.info.filename,
                    opf_hash=epub.core.package_resource.hex_hash,
                    ncx_path=ncx_path,
                    ncx_hash=ncx_hash,
                )
                table.insert_one(epub_hash_item)

            except ValueError as e:
                logger.error(f"ValueError: {str(file)!r}\n{e!r}")
                continue
            except PendingRollbackError as e:
                logger.error(f"PendingRollbackError: {str(file)!r}\n{e!r}")
                break
            except Exception as e:
                logger.error(f"Exception [NON-Uwumtl]: {str(file)!r}\n{e!r}")
                continue
        print_success(str(table.count_rows()))


@app.command("remove-tr")
def remove_stale_translations():
    epub_dir = settings.epub_dir
    uwu_dir = settings.epub_uwumtl_dir
    encrypted_dir = settings.encrypted_epub_dir
    start_time = time.time()
    deleted = 0

    for path_start in (r"D:\EPUB\_translated\for removal", r"D:\EPUB_UWUMTL\_translated\for removal"):
        with EpubHashTable(settings.database_url) as table:
            translated = table.get_many(col(table.model.filepath).startswith(path_start), limit=10000)
            logger.info(f"{path_start=} {len(translated)=}")
            for item in translated:
                duplicates = table.get_many(table.model.opf_hash == item.opf_hash)

                if len(duplicates) == 1:
                    continue

                if len(duplicates) > 2:
                    lines = "\n".join([d.filepath for d in duplicates])
                    logger.warning(f"MULTI - DUPLICATES:\n{lines}")
                    break

                for d in duplicates:
                    if d.filepath.startswith(path_start):
                        path = Path(d.filepath)
                        if path.exists():
                            path.unlink()
                            logger.info(f"DELETE: {d.filepath}")
                            deleted += 1
                            table.delete_one(d)
                        else:
                            logger.error(f"DOES NOT EXIST {path}")

                    else:
                        logger.info(f"REMAIN: {d.filepath}")

    print_success(f"ELAPSED: {time.time() - start_time:.2f} s, DELETED: {deleted}")