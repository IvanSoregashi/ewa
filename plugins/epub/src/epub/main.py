import logging
import time

import typer
from pathlib import Path

from epub.serene_panda import orchestration
from ewa.ui import print_success, print_error
from ewa.cli.print_table import print_table_from_models, print_table_from_dicts
from ewa.cli.progress import DisplayProgress
from ewa.main import settings
from epub.tables import EpubBookTable, EpubContentsTable
from epub.constants import duplicates_directory, epub_dir, serene_panda_fonts_dir
from library.epub.epub_core import EpubSpecification
from library.epub.utils_css import parse_css_urls, replace_css_url
from library.epub.utils_href import posix_relative_href
from library.utils import sanitize_filename
from library.epub.epub import EPUB

app = typer.Typer(help="Epub Plugin")

logger = logging.getLogger("EPUB")


@app.callback()
def setup():
    """Initialize the database on first run."""
    print_success(f"setup callback called, settings:{settings.model_dump_json()}")


@app.command("scanf")
def scan_epubs_in_current_directory(path: Path = typer.Argument(None)):
    """Scans a directory for .epub files."""
    orchestration.scan_folder(path)


@app.command()
def dups(move: bool = typer.Option(False, "-m", "--move"), cleanup: bool = typer.Option(False, "-c", "--cleanup")):
    if cleanup:
        for i in duplicates_directory.iterdir():
            if i.is_dir():
                files = list(i.glob("*.epub"))
                if len(files) == 1:
                    print_success(str(i))
                    EPUB(files[0]).move_original_to(epub_dir, overwrite=False)
                    files = list(i.glob("*.epub"))
                if len(files) == 0:
                    print_success(str(i))
                    i.rmdir()
        return
    with EpubBookTable() as table:
        title_list = table.get_most_common([table.model.title], table.model.serene_panda == 1, more_then=1)
        for title in title_list:
            new_dir = duplicates_directory / sanitize_filename(title)
            new_dir.mkdir(parents=True, exist_ok=True)
            items = table.get_many(table.model.title == title)
            print_table_from_models(title, items)
            if move:
                for item in items:
                    item.to_epub().move_original_to(new_dir, overwrite=False)


@app.command()
def test():
    orchestration.extract_container_files()


@app.command()
def decrypt(epub_path: Path = typer.Argument(None, exists=True)):
    changes_dir = settings.current_dir / "changes"
    changes_dir.mkdir(parents=True, exist_ok=True)

    new_name = epub_path.with_stem(epub_path.stem.replace("(Encoded)", "").strip()).name
    destination = changes_dir / new_name

    with EPUB(epub_path).stream_to(destination) as epub:
        epub.require_specification(EpubSpecification.SERENE_PANDA_ENCRYPTED)

        assert len(epub.core.fonts) == 1, "SEVERAL FONTS FOUND"
        font_resource = epub.core.fonts[0]
        font_resource.write_to_filesystem(serene_panda_fonts_dir / font_resource.hash_prefixed_name)

        epub.core.remove_resource(font_resource)

        for style_resource in epub.core.styles:
            relative_path = posix_relative_href(anchor=style_resource.filename, absolute_href=font_resource.filename)
            if relative_path in parse_css_urls(style_resource.content):
                style_resource.content = replace_css_url(
                    style_resource.content, relative_path, font_resource.hash_prefixed_name
                )
                style_resource.is_modified = True

        dictionary = orchestration.translation_dictionary()
        for content_resource in epub.core.markup_content:
            if not content_resource.is_spine_item():
                logger.warning(f"content_resource {content_resource.filename} is not in the spine")
            content_resource.content = content_resource.content.decode("utf-8").translate(dictionary).encode("utf-8")
            # content_resource.content = pretty_print_bs4_bytes(content_resource.content)
            content_resource.is_modified = True

        epub.core.cleanup()


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


@app.command("rub")
def return_untranslated_back():
    with DisplayProgress(), EpubBookTable() as table:
        orchestration.return_untranslated_back(table)


@app.command("trall")
def translate_everything():
    with EpubBookTable() as table:
        orchestration.translate_all_encrypted(table)


@app.command("trthis")
def translate_this_directory():
    tr = settings.current_dir / "trans"
    tr.mkdir(parents=True, exist_ok=True)
    untr = settings.current_dir / "untrans"
    untr.mkdir(parents=True, exist_ok=True)

    orchestration.translate_epubs_in_directory(settings.current_dir, tr, untr)


@app.command()
def path(epub: Path = typer.Argument(None, exists=True)):
    orchestration.translate_one_epub(epub)


@app.command("formt")
def form_translation():
    orchestration.form_translation()


@app.command()
def ocr():
    orchestration.recognize_letters(settings.current_dir)


@app.command("rfonts")
def render_fonts():
    orchestration.process_all_fonts_mproc(settings.current_dir)


@app.command()
def count(
    files: bool = typer.Option(False, "-f", "--files"),
    rows: bool = typer.Option(False, "-r", "--rows"),
):
    if files:
        print_success(f"Counting epub files in {settings.current_dir}...")
        print_success(f"{len(tuple(Path(settings.current_dir).rglob('*.epub')))} epub files found")
    if rows:
        with EpubContentsTable() as table:
            print_success(f"Counting epub file records in {table.model.__tablename__} SQL table...")
            print_success(f"{table.count_rows()} total rows of files found")
        with EpubBookTable() as table:
            print_success(f"Counting epub file records in {table.model.__tablename__} SQL table...")
            print_success(f"{table.count_rows()} total rows of epubs found")


@app.command()
def drop(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
):
    if files:
        with EpubBookTable() as table:
            table.drop()
            print_success(f"dropped table {table.model.__tablename__}")
    if contents:
        with EpubContentsTable() as table:
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
        with EpubBookTable() as table:
            raw_rows = table.get_many(limit=10)
            if not raw_rows:
                print_error(f"Table {table.model.__tablename__} is empty")
                return
            print_table_from_models("My Library", raw_rows)
    if contents:
        with EpubContentsTable() as table:
            raw_rows = table.get_many(limit=10)
            if not raw_rows:
                print_error(f"Table {table.model.__tablename__} is empty")
                return
            print_table_from_models("My Library", raw_rows)


# Entry point for the plugin loader
def plugin():
    return app
