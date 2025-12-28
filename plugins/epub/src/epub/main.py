import typer
from pathlib import Path
from ewa.ui import print_success, print_error, print_table_from_models, DisplayProgress
from ewa.main import settings
from epub.tables import EpubBookTable, EpubContentsTable
from epub.epub_classes import ScanEpubsInDirectory

app = typer.Typer(help="Epub Plugin")


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
        scanning = ScanEpubsInDirectory(path, workers=2)
        contents_table.write_from_queue_in_thread(scanning.queue)
        book_list = scanning.do_scan_with_progress()
        contents_table.await_write_completion()
        book_table.bulk_insert_models(book_list)


@app.command()
def test():
    with EpubBookTable() as table:
        row = table.read_row(id=-9222855734309247887)
        print(row)
        print(*row.contents, sep="\n")
        row = table.read_row(filesize=3889488)
        print(row)
        print(*row.contents, sep="\n")


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
        with EpubContentsTable() as table:
            print_success(f"Counting epub file records in {table.table_model.__tablename__} SQL table...")
            print_success(f"{table.count_rows()} total rows found")


@app.command()
def drop(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
):
    if files:
        with EpubBookTable() as table:
            table.drop()
            print_success(f"dropped table {table.table_model.__tablename__}")
    if contents:
        with EpubContentsTable() as table:
            table.drop()
            print_success(f"dropped table {table.table_model.__tablename__}")


@app.command("list")
def list_scanned_files(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
    largest: str = typer.Option("", "-l", "--largest"),
):
    """Lists all scanned books."""
    if files:
        with EpubBookTable() as table:
            raw_rows = table.read_rows(limit=10)
            if not raw_rows:
                print_error(f"Table {table.table_model.__tablename__} is empty")
                return
            print_table_from_models("My Library", raw_rows)
    if contents:
        with EpubContentsTable() as table:
            raw_rows = table.read_rows(limit=10)
            if not raw_rows:
                print_error(f"Table {table.table_model.__tablename__} is empty")
                return
            print_table_from_models("My Library", raw_rows)


# Entry point for the plugin loader
def plugin():
    return app
