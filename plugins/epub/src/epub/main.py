from queue import Queue
from concurrent.futures.thread import ThreadPoolExecutor

import typer
import time
from pathlib import Path
from ewa.ui import print_success, print_error, print_table_from_models, DisplayProgress
from ewa.main import settings
from ewa.sqlite_model_table import TERMINATOR
from epub.tables import EpubBookTable, EpubContentsTable
from epub.epub_classes import EPUB, ScanDirectoryEPUB

app = typer.Typer(help="Epub Plugin")


@app.callback()
def setup():
    """Initialize the database on first run."""
    print_success(f"setup callback called, settings:{settings.model_dump_json()}")


@app.command("scanf")
def scan_files():
    """Scans a directory for .epub files."""
    path = settings.current_dir
    print_success(f"Scanning {path}...")
    with DisplayProgress():
        scanning = ScanDirectoryEPUB(path)
        EpubContentsTable().write_from_queue_in_thread(scanning.queue)
        book_list = scanning.do_scan_with_progress()
        if not scanning.queue.empty():
            time.sleep(1)
        EpubBookTable().bulk_insert_models(book_list)


@app.command("scanc")
def scan_contents():
    """Scans a directory for .epub files, reads contents of epub files."""
    table = EpubContentsTable()
    # row = table.read_row()
    path = settings.current_dir
    print_success(f"Scanning {path}...")
    start_time = time.time()
    total_len = len(list(path.rglob("*.epub")))
    if total_len == 0:
        print_error(f"[{time.time() - start_time:>7.2f}] 0 epub files found")
        return
    epubs = map(EPUB, path.rglob("*.epub"))
    q = Queue()
    table.write_in_thread(q)
    with ThreadPoolExecutor() as exec:
        exec.map(lambda x: [q.put(row) for row in x.collect_file_info()], epubs)
    q.put(TERMINATOR)
    print_success(f"[{time.time() - start_time:>7.2f}] {total_len} epubs processed")


@app.command()
def test():
    table = EpubBookTable()
    row = table.read_row(id=-9222855734309247887)
    print(row)
    row = table.read_row(filesize=3889488)
    print(row)


@app.command()
def count(
    files: bool = typer.Option(False, "-f", "--files"),
    rows: bool = typer.Option(False, "-r", "--rows"),
):
    if files:
        print_success(f"Counting epub files in {settings.current_dir}...")
        count = len(tuple(Path(settings.current_dir).rglob("*.epub")))
        print_success(f"{count} epub files found")
    if rows:
        table = EpubContentsTable(echo=False)
        print_success(f"Counting epub file records in {table.table_model.__tablename__} SQL table...")
        print_success(f"{table.count_rows()} total rows found")


@app.command()
def drop(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
):
    if files:
        table = EpubBookTable()
        table.drop()
        print_success(f"dropped table {table.table_model.__tablename__}")
    if contents:
        table = EpubContentsTable()
        table.drop()
        print_success(f"dropped table {table.table_model.__tablename__}")


@app.command("listf")
def list_scanned_files(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
    largest: str = typer.Option("", "-l", "--largest"),
):
    """Lists all scanned books."""
    if files:
        table = EpubBookTable()
        raw_rows = table.read_rows(limit=10)
        if not raw_rows:
            print_error(f"Table {table.table_model.__tablename__} is empty")
            return
        print_table_from_models("My Library", raw_rows)
    if contents:
        print_error("Not Implemented")


# Entry point for the plugin loader
def plugin():
    return app
