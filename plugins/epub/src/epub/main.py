import logging
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import chain

import typer
from pathlib import Path

from pydantic import DirectoryPath
from sqlalchemy.exc import PendingRollbackError
from sqlmodel import col

from epub.serene_panda import orchestration
from epub.serene_panda.orchestration import move_file_preserving_hierarchy
from ewa.ui import print_success, print_error
from ewa.cli.print_table import print_table_from_models, print_table_from_dicts
from ewa.cli.progress import DisplayProgress
from ewa.main import settings
from epub.tables import EpubBookTable, EpubContentsTable, EpubOpfHash, EpubHashTable
from library.epub.epub_core import EpubSpecification
from library.epub.media_type import FileName, EpubRole
from library.epub.utils import to_hex_hash
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
    start_time = time.time()
    skipped = 0
    moved = 0
    sync_dir = Path(r"C:\Users\Ivan\Sync\Books")
    move = False
    for file in sync_dir.rglob("*.epub"):
        latest_time = time.time()
        if file.is_dir():
            logger.info(f"SKIPPED DIR: {str(file)!r}")
            continue
        try:
            epub = EPUB(file)
            with epub.source.open():
                font = epub.source.getinfo(FileName.SP_FONT)
                font2 = epub.source.getinfo("SerenePanda.ttf")
                font3 = epub.source.getinfo("serenepanda.ttf")

                if font is not None or font2 is not None or font3 is not None:
                    move = True
                if not move:
                    fonts = epub.resources.by_role(EpubRole.FONT)
                    if len(fonts):
                        for font in fonts:
                            if "serenepanda" in font.info.filename.lower():
                                logger.warning(
                                    f"FOUND FONT {time.time() - latest_time:.3f}s {time.time() - start_time:.3f}s: {font.info.filename}"
                                )
                                move = True

        except ValueError as e:
            logger.error(f"ValueError: {str(file)!r} (SKIPPING)\n{e!r}")
            continue
        except (IndexError, AssertionError) as e:
            logger.error(f"RecoverableError: {str(file)!r} (SKIPPING)\n{e!r}")
            break
        except PermissionError as e:
            logger.error(f"PermissionError: {str(file)!r} (SKIPPING)\n{e!r}")
            break
        except Exception as e:
            logger.error(f"Exception: {str(file)!r}\n{e!r}")
            break

        if move:
            move_file_preserving_hierarchy(file, settings.encrypted_epub_dir)
            moved += 1
            move = False
        else:
            skipped += 1
            logger.info(
                f"SKIPPED({skipped:>03}) {time.time() - latest_time:.3f}s {time.time() - start_time:.3f}s: {str(file)!r}"
            )

    logger.warning(f"SKIPPED: {skipped}, MOVED: {moved}, ELAPSED: {time.time() - start_time}")


@app.command("mostc")
def most_common():
    with EpubHashTable(settings.database_url) as table:
        common = table.get_most_common(group_fields=["author"], more_then=10)
        print(common)


@app.command("scan-hash")
def scan_for_hashes(path: DirectoryPath = typer.Option(None, "-p")):
    start_time = time.time()

    with EpubHashTable(settings.database_url) as table:
        table.drop()
        table.create()
        for directory in Path("D:/").glob("*EPUB*"):
            for file in directory.rglob("*.epub"):
                try:
                    file = file.absolute()
                    epub = EPUB(file)
                    package_document = epub.core.package_document

                    ncx_path = None
                    ncx_hash = None
                    ncx_resource = epub.core._ncx_resource
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
                except AssertionError as e:
                    logger.error(f"AssertionError: {str(file)!r}\n{e!r}")
                    move_file_preserving_hierarchy(file, directory / "_class_fails")
                    continue
                except PendingRollbackError as e:
                    logger.error(f"PendingRollbackError: {str(file)!r}\n{e!r}")
                    break
                except Exception as e:
                    logger.error(f"Exception: {str(file)!r}\n{e!r}")
                    continue

            logger.info(f"ELAPSED: {time.time() - start_time:.2f} {str(table.count_rows())=}")


@app.command("list-some")
def list_some_hashes(
    a: str = typer.Option(None, "-a"), i: str = typer.Option(None, "-i"), p: str = typer.Option(None, "-p")
):
    clause = []
    with EpubHashTable(settings.database_url) as table:
        if a is not None:
            clause.append(table.model.author == a)
        if p is not None:
            clause.append(col(table.model.filepath).contains(p))
        if i is not None:
            clause.append(col(table.model.identifier).contains(i))
        all_items = table.get_many(*clause, limit=10000)
        logger.info(f"{len(all_items)=}")
        print_table_from_models(f"filters = {a}", all_items)


@app.command("move-some")
def move_some_files(
    d: str = typer.Option(None, "-d"),
    a: str = typer.Option(None, "-a"),
    i: str = typer.Option(None, "-i"),
    p: str = typer.Option(None, "-p"),
):
    epub_dir = settings.epub_dir
    destination_dir = settings.D_DISK / f"EPUB_{d}"
    # destination_dir = settings.epub_uwumtl_dir
    start_time = time.time()
    moved = 0

    dir_list = list(settings.D_DISK.glob("*EPUB*"))

    clause = []
    with EpubHashTable(settings.database_url) as table:
        if a is not None:
            clause.append(table.model.author == a)
        if p is not None:
            clause.append(col(table.model.filepath).contains(p))
        if i is not None:
            clause.append(col(table.model.identifier).contains(i))
        all_items = table.get_many(*clause, limit=10000)
        logger.info(f"{len(all_items)=}")

        for item in all_items:
            file = Path(item.filepath)
            directories = [dr for dr in file.parents if dr in dir_list]
            assert len(directories) == 1
            directory = directories[0]
            if not file.is_relative_to(directory):
                logger.info(f"NOT RELATIVE [{d}]: {str(file)!r}")
                continue
            relative_path = file.relative_to(directory)
            new_path = destination_dir / relative_path
            if new_path.exists():
                logger.info(f"SKIPPING [{d}]: {str(file)!r}")
                continue
            new_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                logger.info(f"MOVING [{d}]: {str(file)!r} -> {str(new_path)!r}")
                shutil.move(str(file), str(new_path))
                new_item = item.model_copy(deep=True, update={"filepath": str(new_path)})
                table.insert_one(new_item)
                table.delete_one(item)
                moved += 1
            except Exception as e:
                logger.error(f"{str(file)!r}\n{e!r}")

    print_success(f"MOVED: {moved}, ELAPSED: {time.time() - start_time:.2f} s")


@app.command("move-ne")
def move_not_epubs():
    epub_dir = settings.epub_dir
    destination = (settings.D_DISK / "OTHER_BOOKS").absolute()
    destination.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    moved = 0
    sync_dir = Path(r"C:\Users\Ivan\Sync\Books")
    dirs = list(epub_dir.rglob("*"))
    # dirs = list(sync_dir.rglob("*.epub"))

    for file in dirs:
        if file.is_dir():
            logger.info(f"SKIPPED DIR: {str(file)!r}")
            continue
        if file.suffix.lower() == ".epub":
            logger.info(f"SKIPPED EPUB: {str(file)!r}")
            continue
        move_file_preserving_hierarchy(file, destination)
        moved += 1

    logger.info(f"MOVED: {moved}, ELAPSED: {time.time() - start_time}")


@app.command("hash-dups")
def count_hash_duplicates():
    start_time = time.time()
    filehash = {}
    read_files = 0
    errors = 0
    dirpath = Path("D:/OTHER_BOOKS")
    for file in dirpath.rglob("*"):
        if file.is_dir():
            continue

        try:
            fhash = to_hex_hash(file.read_bytes())
            filehash.setdefault(fhash, []).append(str(file))
            read_files += 1

        except Exception as e:
            logger.error(f"Exception: {str(file)!r}\n{e!r}")
            errors += 1
            continue

    logger.warning(
        f"READ/HASHES: {read_files}/{len(filehash)}, DIFF: {read_files - len(filehash)}, ERRORS: {errors}, ELAPSED: {time.time() - start_time:.2f}s"
    )

    deleted_files = 0
    deleted_bytes = 0
    for fhash, files in filehash.items():
        if len(files) == 1:
            continue

        logger.info(f"DUPLICATES {len(files)} - {fhash}")
        for i, f in enumerate(files):
            logger.info(f"\t {i}) {f!r}")
        remain = input("Choose index of remaining file (NAN to SKIP): ")

        try:
            remain = int(remain)
        except ValueError:
            logger.warning(f"Skipping {fhash}")
            continue

        for i, f in enumerate(files):
            if i != remain:
                p = Path(f)
                file_size = p.stat().st_size
                try:
                    p.unlink()
                    deleted_files += 1
                    deleted_bytes += file_size
                    logger.warning(f"REMOVED: {f!r} ({file_size / (1024 * 1024):.2f} MB)")
                except Exception as e:
                    logger.error(f"Exception: {str(f)!r}\n{e!r}")
                    pass

    logger.warning(
        f"REMOVED TOTAL OF: {deleted_files} files, {deleted_bytes / (1024 * 1024):.2f} MB, ELAPSED: {time.time() - start_time:.2f}s"
    )
