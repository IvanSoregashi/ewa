import logging

import typer
from pathlib import Path

from ewa.ui import print_success, print_error
from ewa.cli.print_table import print_table_from_models
from ewa.cli.progress import DisplayProgress, track_batch_queue, track_batch_sized
from ewa.main import settings
from epub.tables import EpubBookTable, EpubContentsTable
from epub.epub_classes import ScanEpubsInDirectory, EPUB, extract_font_files
from epub.constants import duplicates_dir, epub_dir
from library.database.sqlite_model_table import TERMINATOR
from library.utils import sanitize_filename

app = typer.Typer(help="Epub Plugin")

logger = logging.getLogger("EPUB")


@app.callback()
def setup():
    """Initialize the database on first run."""
    print_success(f"setup callback called, settings:{settings.model_dump_json()}")


@app.command("scanf")
def scan_epubs_in_current_directory():
    """Scans a directory for .epub files."""
    path = settings.current_dir
    print_success(f"Scanning {path}...")
    with DisplayProgress(), EpubContentsTable() as contents_table, EpubBookTable() as book_table:
        scanning = ScanEpubsInDirectory(path, workers=4)
        contents_table.write_from_queue_in_thread(track_batch_queue(scanning.queue, TERMINATOR))
        book_list = scanning.do_scan_with_progress()
        contents_table.await_write_completion()
        book_table.upsert_many_dicts(track_batch_sized([row.model_dump() for row in book_list]))


@app.command()
def dups(move: bool = typer.Option(False, "-m", "--move"), cleanup: bool = typer.Option(False, "-c", "--cleanup")):
    if cleanup:
        for i in duplicates_dir.iterdir():
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
        title_list = table.get_most_common([table.model.title], table.model.serene_panda == True, more_then=1)
        for title in title_list:
            new_dir = duplicates_dir / sanitize_filename(title)
            new_dir.mkdir(parents=True, exist_ok=True)
            items = table.get_many(table.model.title == title)
            print_table_from_models(title, items)
            if move:
                for item in items:
                    item.to_epub().move_original_to(new_dir, overwrite=False)


@app.command()
def test():
    with DisplayProgress(), EpubBookTable() as table:
        extract_font_files(table)


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
            print_success(f"{table.count_rows()} total rows found")


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
